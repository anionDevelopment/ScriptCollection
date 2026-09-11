import os
import re
import json
import time
import uuid
import base64
import tarfile
import urllib.request
import urllib.error
import http.client
from enum import Enum
from ..GeneralUtilities import GeneralUtilities
from ..ScriptCollectionCore import ScriptCollectionCore
from ..SCLog import LogLevel

#Duration for which the client keeps asking a runner which does not answer before it states that the delegated build has
#no result here. A job runs on the runner independently of the connection to the client, so an interruption of that
#connection (for example a restart of a reverse-proxy in front of the runner) does not stop the build - giving up
#immediately would discard a build which is still producing a result. A longer interruption is not bridged, so that a
#build always ends with a statement instead of with an endless wait.
_tolerated_interruption_of_the_connection_to_the_runner_in_seconds: int = 300

#Timeout of a request whose answer the runner produces without doing anything long-running for it (the state of a job,
#its log, its deletion, the operating-system a runner provides). It is the timeout of a single operation on the
#connection and not the duration of the whole request, so it is the time after which a connection which does not
#transport anything any more counts as interrupted.
_timeout_of_a_request_in_seconds: int = 300

#Timeout of a request whose answer the runner produces only after something long-running which transports nothing while
#it runs: the result-archive of a job contains the complete build-output of a codeunit and is packed completely before
#its first byte is sent, which takes minutes for a large build-output. This has to stay above the read-timeout of a
#reverse-proxy in front of a runner, so that its gateway-timeout - a defined answer - arrives instead of the client
#giving up on the connection first.
_timeout_of_a_long_running_request_in_seconds: int = 60*60


class RunnerOperatingSystem(Enum):
    """Operating-system a remote-build-runner provides. The value is the token exchanged over the wire (see the runner's
    'GET /os'-endpoint)."""
    Windows = "Windows"
    MacOS = "MacOS"
    Linux = "Linux"
    Android = "Android"
    IOS = "IOS"


class RunnerEndpoint:
    url: str = None
    username: str = None
    password: str = None

    def __init__(self, url: str, username: str, password: str):
        self.url = url.rstrip("/")
        self.username = username
        self.password = password


class RunnerRequestFailedError(ValueError):
    """A runner answered a request with an error-status. The request reached the runner, so this is a defined answer of
    the runner and not a problem of the connection to it (see RunnerNotReachableError for that)."""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


class RunnerNotReachableError(ValueError):
    """A request did not reach a runner, or its answer did not reach the client, for example because the connection was
    reset or because the host is not resolvable. In contrast to RunnerRequestFailedError this states nothing about the
    state of a job on the runner: a job which was started there before keeps running."""


class TFCPS_RemoteBuild:
    """Delegates an operating-system-bound build-step to a remote task-runner (see SCTaskRunnerWindows/SCTaskRunnerMacOS):
    the whole repository (including the .git-folder, uncommitted changes and git-ignored files) is sent as a tar-archive
    over HTTPS to the runner, the runner runs the given program on its (correct) operating-system, and afterwards only the
    folder in which that build-step produces its result is written back into the local repository. Everything else which
    changed in the workspace of the runner stays there: it is state of that machine (its toolchain-paths, its caches) and
    not a result, and a local repository is something a developer works in and which therefore must not be replaced."""

    __sc: ScriptCollectionCore = None

    def __init__(self, sc: ScriptCollectionCore):
        self.__sc = sc

    @GeneralUtilities.check_arguments
    def has_any_runner_configured(self) -> bool:
        """Whether at least one remote-build-runner is configured (see run_program_on_runner)."""
        return len(self.__load_runner_endpoints()) > 0

    @GeneralUtilities.check_arguments
    def run_program_on_runner(self, required_os: RunnerOperatingSystem, repository_folder: str, codeunit_name: str, program: str, arguments: list[str], working_directory: str, result_folder: str, poll_interval_in_seconds: int = 3, timeout_in_seconds: int = 60*60) -> None:
        endpoints = self.__load_runner_endpoints()
        if len(endpoints) == 0:
            raise ValueError("No remote-build-runner is configured. Define runners either in "
                             f"'{os.path.join(self.__sc.get_scriptcollection_configuration_folder(), 'TFCPS', 'Runner.csv')}' "
                             "(one line per runner in the format 'url;user;password') or via environment-variables "
                             "'Runner_<name>_URL', 'Runner_<name>_Username' and 'Runner_<name>_Password'.")
        endpoint = self.__select_runner_for_os(endpoints, required_os)
        working_directory_relative = os.path.relpath(working_directory, repository_folder).replace("\\", "/")
        result_folder_relative = os.path.relpath(result_folder, repository_folder).replace("\\", "/")
        self.__sc.log.log(f"Delegate '{program} {' '.join(arguments)}' (codeunit '{codeunit_name}', folder '{working_directory_relative}', result-folder '{result_folder_relative}') to the {required_os.value}-runner at {endpoint.url}...")
        archive_file = self.__create_repository_archive(repository_folder)
        job_id: str = None
        try:
            metadata_headers = {
                "Content-Type": "application/octet-stream",
                "X-Codeunit-Name": codeunit_name,
                "X-Program": program,
                "X-Arguments": base64.b64encode(json.dumps(arguments).encode("utf-8")).decode("ascii"),
                "X-Working-Directory": working_directory_relative,
                "X-Result-Folder": result_folder_relative,
            }
            with open(archive_file, "rb") as archive_content:
                archive_bytes = archive_content.read()
            _, submit_response = self.__http(endpoint, "POST", "/jobs", _timeout_of_a_request_in_seconds, metadata_headers, archive_bytes)
            job_id = json.loads(submit_response.decode("utf-8"))["job_id"]
            self.__wait_for_job(endpoint, job_id, required_os, poll_interval_in_seconds, timeout_in_seconds)
            #The result-archive is packed completely before it is sent, which transports nothing while it runs - hence
            #the timeout of a long-running request here.
            _, result_bytes = self.__http_of_running_job(endpoint, "GET", f"/jobs/{job_id}/result", _timeout_of_a_long_running_request_in_seconds, poll_interval_in_seconds)
            self.__write_result_into_the_repository(result_bytes, result_folder)
        finally:
            if job_id is not None:
                try:
                    # Triggers the runner to delete its (isolated) workspace for this job immediately after the result was fetched.
                    self.__http(endpoint, "DELETE", f"/jobs/{job_id}", _timeout_of_a_request_in_seconds)
                except Exception as exception:
                    self.__sc.log.log_exception(f"Could not delete remote job '{job_id}' on runner '{endpoint.url}'.", exception, LogLevel.Warning)
            GeneralUtilities.ensure_file_does_not_exist(archive_file)

    @GeneralUtilities.check_arguments
    def __wait_for_job(self, endpoint: RunnerEndpoint, job_id: str, required_os: RunnerOperatingSystem, poll_interval_in_seconds: int, timeout_in_seconds: int) -> None:
        start_time = time.time()
        already_printed_log_length = 0
        while True:
            status = self.__get_job_status(endpoint, job_id, required_os, poll_interval_in_seconds)
            _, log_bytes = self.__http_of_running_job(endpoint, "GET", f"/jobs/{job_id}/logs", _timeout_of_a_request_in_seconds, poll_interval_in_seconds)
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
    def __get_job_status(self, endpoint: RunnerEndpoint, job_id: str, required_os: RunnerOperatingSystem, poll_interval_in_seconds: int) -> dict:
        """Asks the runner for the state of the job. A runner which does not know the job (any more) gets an own message:
        a runner holds its jobs in memory only, so that is what a restart of the runner while a job was running looks
        like from here, and the status-code alone does not state that the delegated build is gone with it."""
        try:
            _, status_bytes = self.__http_of_running_job(endpoint, "GET", f"/jobs/{job_id}", _timeout_of_a_request_in_seconds, poll_interval_in_seconds)
        except RunnerRequestFailedError as request_failed_error:
            if request_failed_error.status == 404:
                raise ValueError(f"The {required_os.value}-runner at '{endpoint.url}' does not know the job '{job_id}' (any more), so the delegated build has no result. A runner holds its jobs in memory only: when it is restarted while a job runs, the job and its build are gone with it.") from None
            raise
        return json.loads(status_bytes.decode("utf-8"))

    @GeneralUtilities.check_arguments
    def __http_of_running_job(self, endpoint: RunnerEndpoint, method: str, path: str, timeout_in_seconds: int, retry_interval_in_seconds: int) -> tuple[int, bytes]:
        """Does a request which concerns a job that already exists on the runner and which can therefore be repeated
        without side-effects (it neither starts a job twice nor changes one). The job keeps running on the runner while
        the connection to it is interrupted, so an interruption which is over within
        _tolerated_interruption_of_the_connection_to_the_runner_in_seconds is bridged here by repeating the request
        instead of giving up a build which still produces a result. A longer interruption ends in a
        RunnerNotReachableError which states that the result of the build is unknown here. An answer of the runner -
        an error-status included - is not an interruption and is returned respectively raised immediately."""
        moment_of_the_first_unreachable_request: float = None
        while True:
            try:
                result = self.__http(endpoint, method, path, timeout_in_seconds)
                if moment_of_the_first_unreachable_request is not None:
                    self.__sc.log.log(f"The runner '{endpoint.url}' is reachable again.", LogLevel.Information)
                return result
            except RunnerNotReachableError as not_reachable_error:
                if moment_of_the_first_unreachable_request is None:
                    moment_of_the_first_unreachable_request = time.time()
                    self.__sc.log.log(f"{not_reachable_error} The job runs on the runner independently of this connection, so the request is repeated for at most {_tolerated_interruption_of_the_connection_to_the_runner_in_seconds} seconds.", LogLevel.Warning)
                if time.time()-moment_of_the_first_unreachable_request > _tolerated_interruption_of_the_connection_to_the_runner_in_seconds:
                    raise RunnerNotReachableError(f"The runner '{endpoint.url}' was not reachable for {_tolerated_interruption_of_the_connection_to_the_runner_in_seconds} seconds while the request '{method} {path}' was repeated (last reason: {not_reachable_error}). The delegated build therefore has no result here; it may still be running on the runner.") from None
                time.sleep(retry_interval_in_seconds)

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
    def __write_result_into_the_repository(self, result_bytes: bytes, result_folder: str) -> None:
        """Writes what the runner produced into the folder of the local repository in which the build-step produces its
        result, so the build can continue with it as if it had been produced here.

        Nothing is deleted for this. Before, the whole codeunit-folder was replaced by the one of the runner, which
        deleted everything of that codeunit which is not part of the answer of the runner - including files which are
        not in git and can therefore not be restored - and which on Windows can not even complete: the build-script of
        the codeunit runs in a folder below the codeunit, and a folder a process runs in can not be removed there, so
        the deletion failed in the middle and left the codeunit incomplete. It is also not what is wanted: what changes
        in the workspace of the runner besides the result is state of that machine (its toolchain-paths, its caches),
        which has no business in the repository of a developer."""
        result_archive = os.path.join(GeneralUtilities.get_temp_folder(), f"sc-remotebuild-result-{uuid.uuid4()}.tar.gz")
        try:
            GeneralUtilities.write_binary_to_file(result_archive, result_bytes)
            GeneralUtilities.ensure_directory_exists(result_folder)
            with tarfile.open(result_archive, "r:gz") as tar:
                tar.extractall(result_folder, filter="fully_trusted")
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
        runners_which_could_not_be_reached: list[str] = []
        for endpoint in endpoints:
            try:
                _, os_bytes = self.__http(endpoint, "GET", "/os", _timeout_of_a_request_in_seconds)
                if os_bytes.decode("utf-8").strip() == required_os.value:
                    return endpoint
            except RunnerNotReachableError as not_reachable_error:
                #A runner which can not be reached is something else than one which does not provide the required
                #operating-system: it is configured and may well be the right one, which is unknown while it does not
                #answer. It is therefore collected here and stated as the reason if no runner can be selected at all.
                runners_which_could_not_be_reached.append(str(not_reachable_error))
                self.__sc.log.log(str(not_reachable_error), LogLevel.Warning)
            except Exception as exception:
                self.__sc.log.log_exception(f"Could not query the operating-system of the runner '{endpoint.url}'.", exception, LogLevel.Warning)
        if len(runners_which_could_not_be_reached) == len(endpoints):
            raise ValueError(f"None of the configured remote-build-runners could be reached, so whether one of them provides the required operating-system '{required_os.value}' is unknown: {' '.join(runners_which_could_not_be_reached)}")
        raise ValueError(f"No configured remote-build-runner provides the required operating-system '{required_os.value}'.")

    @GeneralUtilities.check_arguments
    def __http(self, endpoint: RunnerEndpoint, method: str, path: str, timeout_in_seconds: int, extra_headers: dict = None, body: bytes = None) -> tuple[int, bytes]:
        request = urllib.request.Request(endpoint.url + path, data=body, method=method)
        authorization_token = base64.b64encode(f"{endpoint.username}:{endpoint.password}".encode("utf-8")).decode("ascii")
        request.add_header("Authorization", f"Basic {authorization_token}")
        if extra_headers is not None:
            for header_name, header_value in extra_headers.items():
                request.add_header(header_name, header_value)
        try:
            with urllib.request.urlopen(request, timeout=timeout_in_seconds) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as http_error:
            error_body = http_error.read().decode("utf-8", errors="replace")
            raise RunnerRequestFailedError(f"The runner-request '{method} {path}' failed with status {http_error.code}: {error_body}", http_error.code) from http_error
        except (OSError, http.client.HTTPException) as connection_error:
            #Everything which prevented an answer of the runner: urllib.error.URLError (which is an OSError) covers a
            #connection which was refused, reset or not establishable at all, http.client.HTTPException covers an answer
            #which was cut off while it was read. Both are stated as one error which names what was requested from whom.
            #The cause is deliberately not chained: its message is part of the message here, while its traceback consists
            #of the internals of urllib only and states nothing about the delegated build.
            raise RunnerNotReachableError(f"The runner '{endpoint.url}' could not be reached for the request '{method} {path}': {connection_error}") from None
