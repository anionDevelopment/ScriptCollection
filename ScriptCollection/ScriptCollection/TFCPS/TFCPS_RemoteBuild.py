import os
import re
import json
import time
import uuid
import base64
import tarfile
import urllib.request
import urllib.error
from enum import Enum
from ..GeneralUtilities import GeneralUtilities
from ..ScriptCollectionCore import ScriptCollectionCore
from ..SCLog import LogLevel


class RunnerOperatingSystem(Enum):
    """Operating-system a remote-build-runner provides. The value is the token exchanged over the wire (see the runner's
    'GET /os'-endpoint)."""
    Windows = "Windows"
    MacOS = "MacOS"
    Linux = "Linux"


class RunnerEndpoint:
    url: str = None
    username: str = None
    password: str = None

    def __init__(self, url: str, username: str, password: str):
        self.url = url.rstrip("/")
        self.username = username
        self.password = password


class TFCPS_RemoteBuild:
    """Delegates an operating-system-bound build-step to a remote task-runner (see SCTaskRunnerWindows/SCTaskRunnerMacOS):
    the whole repository (including the .git-folder, uncommitted changes and git-ignored files) is sent as a tar-archive
    over HTTPS to the runner, the runner runs the given program on its (correct) operating-system, and afterwards only the
    codeunit-folder is mirrored back into the local repository (a build-script must by definition not change anything
    outside its codeunit-folder, so mirroring just that folder is sufficient and keeps the round-trip small)."""

    __sc: ScriptCollectionCore = None

    def __init__(self, sc: ScriptCollectionCore):
        self.__sc = sc

    @GeneralUtilities.check_arguments
    def run_program_on_runner(self, required_os: RunnerOperatingSystem, repository_folder: str, codeunit_name: str, program: str, arguments: list[str], working_directory: str, poll_interval_in_seconds: int = 3, timeout_in_seconds: int = 60*60) -> None:
        endpoints = self.__load_runner_endpoints()
        if len(endpoints) == 0:
            raise ValueError("No remote-build-runner is configured. Define runners either in "
                             f"'{os.path.join(self.__sc.get_scriptcollection_configuration_folder(), 'TFCPS', 'Runner.csv')}' "
                             "(one line per runner in the format 'url;user;password') or via environment-variables "
                             "'Runner_<name>_URL', 'Runner_<name>_Username' and 'Runner_<name>_Password'.")
        endpoint = self.__select_runner_for_os(endpoints, required_os)
        working_directory_relative = os.path.relpath(working_directory, repository_folder).replace("\\", "/")
        self.__sc.log.log(f"Delegate '{program} {' '.join(arguments)}' (codeunit '{codeunit_name}', folder '{working_directory_relative}') to the {required_os.value}-runner at {endpoint.url}...")
        archive_file = self.__create_repository_archive(repository_folder)
        job_id: str = None
        try:
            metadata_headers = {
                "Content-Type": "application/octet-stream",
                "X-Codeunit-Name": codeunit_name,
                "X-Program": program,
                "X-Arguments": base64.b64encode(json.dumps(arguments).encode("utf-8")).decode("ascii"),
                "X-Working-Directory": working_directory_relative,
            }
            with open(archive_file, "rb") as archive_content:
                archive_bytes = archive_content.read()
            _, submit_response = self.__http(endpoint, "POST", "/jobs", metadata_headers, archive_bytes)
            job_id = json.loads(submit_response.decode("utf-8"))["job_id"]
            self.__wait_for_job(endpoint, job_id, required_os, poll_interval_in_seconds, timeout_in_seconds)
            _, result_bytes = self.__http(endpoint, "GET", f"/jobs/{job_id}/result")
            self.__mirror_codeunit_folder_from_result(result_bytes, repository_folder, codeunit_name)
        finally:
            if job_id is not None:
                try:
                    # Triggers the runner to delete its (isolated) workspace for this job immediately after the result was fetched.
                    self.__http(endpoint, "DELETE", f"/jobs/{job_id}")
                except Exception as exception:
                    self.__sc.log.log_exception(f"Could not delete remote job '{job_id}' on runner '{endpoint.url}'.", exception, LogLevel.Warning)
            GeneralUtilities.ensure_file_does_not_exist(archive_file)

    @GeneralUtilities.check_arguments
    def __wait_for_job(self, endpoint: RunnerEndpoint, job_id: str, required_os: RunnerOperatingSystem, poll_interval_in_seconds: int, timeout_in_seconds: int) -> None:
        start_time = time.time()
        already_printed_log_length = 0
        while True:
            _, status_bytes = self.__http(endpoint, "GET", f"/jobs/{job_id}")
            status = json.loads(status_bytes.decode("utf-8"))
            _, log_bytes = self.__http(endpoint, "GET", f"/jobs/{job_id}/logs")
            log_text = log_bytes.decode("utf-8", errors="replace")
            if len(log_text) > already_printed_log_length:
                for line in GeneralUtilities.string_to_lines(log_text[already_printed_log_length:]):
                    self.__sc.log.log(line, LogLevel.Information)
                already_printed_log_length = len(log_text)
            state = status["state"]
            if state in ("completed", "failed"):
                exitcode = status.get("exitcode")
                if state == "failed" or (exitcode is not None and exitcode != 0):
                    raise ValueError(f"The remote build on the {required_os.value}-runner failed (exitcode {exitcode}). See the runner-log above for details.")
                return
            if time.time() - start_time > timeout_in_seconds:
                raise ValueError(f"The remote build on the {required_os.value}-runner did not finish within {timeout_in_seconds} seconds.")
            time.sleep(poll_interval_in_seconds)

    @GeneralUtilities.check_arguments
    def __create_repository_archive(self, repository_folder: str) -> str:
        # Pack the entire repository-working-tree (including .git, uncommitted changes and git-ignored files) so the runner
        # has the exact same state - including secrets that are required e.g. for signing windows-builds. Uses tarfile so
        # it works identically on Windows and Linux (scbuildcodeunits runs on both) and preserves symlinks/permissions.
        archive_file = os.path.join(GeneralUtilities.get_temp_folder(), f"sc-remotebuild-payload-{uuid.uuid4()}.tar.gz")
        with tarfile.open(archive_file, "w:gz") as tar:
            tar.add(repository_folder, arcname=".")
        return archive_file

    @GeneralUtilities.check_arguments
    def __mirror_codeunit_folder_from_result(self, result_bytes: bytes, repository_folder: str, codeunit_name: str) -> None:
        # Mirror the codeunit-folder from the runner-result into the local repository: the local codeunit-folder is replaced
        # entirely by the runner's post-build codeunit-folder. This makes it look exactly as if the runner had built locally,
        # including files the runner added, changed or deleted (regardless of whether they are git-ignored).
        local_codeunit_folder = os.path.join(repository_folder, codeunit_name)
        result_archive = os.path.join(GeneralUtilities.get_temp_folder(), f"sc-remotebuild-result-{uuid.uuid4()}.tar.gz")
        try:
            GeneralUtilities.write_binary_to_file(result_archive, result_bytes)
            GeneralUtilities.ensure_directory_does_not_exist(local_codeunit_folder)
            GeneralUtilities.ensure_directory_exists(local_codeunit_folder)
            with tarfile.open(result_archive, "r:gz") as tar:
                tar.extractall(local_codeunit_folder, filter="fully_trusted")
        finally:
            GeneralUtilities.ensure_file_does_not_exist(result_archive)

    @GeneralUtilities.check_arguments
    def __load_runner_endpoints(self) -> list[RunnerEndpoint]:
        endpoints: list[RunnerEndpoint] = []
        # Source 1 (primarily for developer-clients): a csv-file with one line per runner in the format "url;user;password".
        csv_file = os.path.join(self.__sc.get_scriptcollection_configuration_folder(), "TFCPS", "Runner.csv")
        if os.path.isfile(csv_file):
            for line in GeneralUtilities.read_lines_from_file(csv_file):
                stripped_line = line.strip()
                if stripped_line == GeneralUtilities.empty_string or stripped_line.startswith("#"):
                    continue
                parts = stripped_line.split(";")
                if len(parts) < 3 or parts[0].strip() == GeneralUtilities.empty_string:
                    continue
                endpoints.append(RunnerEndpoint(parts[0].strip(), parts[1].strip(), parts[2].strip()))
        # Source 2 (primarily for the build-pipeline): environment-variables "Runner_<name>_URL/_Username/_Password".
        # The lookup is case-insensitive because Windows exposes environment-variable-names upper-cased via os.environ.
        environment_variables_upper = {name.upper(): value for name, value in os.environ.items()}
        url_env_pattern = re.compile(r"^RUNNER_(.+?)_URL$")
        for env_var_name, env_var_value in environment_variables_upper.items():
            match = url_env_pattern.match(env_var_name)
            if match is None:
                continue
            runner_name = match.group(1)
            url = (env_var_value or GeneralUtilities.empty_string).strip()
            if url == GeneralUtilities.empty_string:
                continue
            username = (environment_variables_upper.get(f"RUNNER_{runner_name}_USERNAME") or GeneralUtilities.empty_string).strip()
            password = (environment_variables_upper.get(f"RUNNER_{runner_name}_PASSWORD") or GeneralUtilities.empty_string).strip()
            endpoints.append(RunnerEndpoint(url, username, password))
        return endpoints

    @GeneralUtilities.check_arguments
    def __select_runner_for_os(self, endpoints: list[RunnerEndpoint], required_os: RunnerOperatingSystem) -> RunnerEndpoint:
        # The configuration does not state which runner provides which operating-system, so each configured runner is asked
        # (via its "GET /os"-endpoint) and the first one matching the required operating-system is used.
        for endpoint in endpoints:
            try:
                _, os_bytes = self.__http(endpoint, "GET", "/os")
                if os_bytes.decode("utf-8").strip() == required_os.value:
                    return endpoint
            except Exception as exception:
                self.__sc.log.log_exception(f"Could not query the operating-system of the runner '{endpoint.url}'.", exception, LogLevel.Warning)
        raise ValueError(f"No configured remote-build-runner provides the required operating-system '{required_os.value}'.")

    @GeneralUtilities.check_arguments
    def __http(self, endpoint: RunnerEndpoint, method: str, path: str, extra_headers: dict = None, body: bytes = None) -> tuple[int, bytes]:
        request = urllib.request.Request(endpoint.url + path, data=body, method=method)
        authorization_token = base64.b64encode(f"{endpoint.username}:{endpoint.password}".encode("utf-8")).decode("ascii")
        request.add_header("Authorization", f"Basic {authorization_token}")
        if extra_headers is not None:
            for header_name, header_value in extra_headers.items():
                request.add_header(header_name, header_value)
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as http_error:
            error_body = http_error.read().decode("utf-8", errors="replace")
            raise ValueError(f"The runner-request '{method} {path}' failed with status {http_error.code}: {error_body}") from http_error
