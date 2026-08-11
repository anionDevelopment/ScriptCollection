import json
import os
import re
import socket
from ..GeneralUtilities import GeneralUtilities
from ..ScriptCollectionCore import ScriptCollectionCore
from .TFCPS_CodeUnitSpecific_Base import TFCPS_CodeUnitSpecific_Base


class TFCPS_VisualRegressionTests:
    """Executes the visual-regression-tests of a codeunit in the playwright-container.

    The tests are always executed in a container and never directly on the host. Reason: a screenshot depends on
    the operating-system (font-rendering and antialiasing, the available fonts, the rendering of form-controls and
    scrollbars), and the resulting difference is far bigger than the tolerance such a comparison can have. Without
    a defined environment a baseline-screenshot would only be usable on the operating-system it was generated on,
    which would mean one set of baseline-screenshots per operating-system and a pipeline-result which a developer
    can not reproduce.

    The application under test can be provided in two ways:
    - The playwright-configuration of the codeunit starts it itself (its "webServer"-setting). This is possible
      when the application can be started inside the playwright-container, which is the case for a web-frontend
      whose development-server is started by npm.
    - The caller starts it before calling "run" and passes "application_runs_outside_of_container". This is
      required when the application can not be started inside the playwright-container, for example because it
      needs a runtime which that container does not contain.

    The used image is defined as "Playwright" in ".ScriptCollection/OCIImages/ImageDefinition.csv" of the
    repository, like the images of all other tools which are used by the build."""

    __image_name: str = "Playwright"

    # The image contains the browsers of exactly one playwright-version, so the version of the
    # "@playwright/test"-package of the codeunit has to be the same one. Otherwise playwright would look for
    # browsers which are not contained in the image.
    __tag_pattern_with_version_of_playwright = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)")

    # The folder the codeunit is mounted to if the tests are started directly on the host.
    __codeunit_folder_in_container: str = "/codeunit"

    # The folder playwright writes the screenshots of failed testcases to. Playwright empties this folder at the
    # beginning of every run.
    __test_results_folder_relative_path: str = "Other/Artifacts/VisualRegressionTestResults"

    # The folder the screenshots of failed testcases are preserved in. Both folders are located in
    # "Other/Artifacts", which is ignored by git.
    __failed_testcases_folder_relative_path: str = "Other/Artifacts/VisualRegressionTestFailures"

    # The name of the environment-variable which tells the testcases under which hostname the application under
    # test is reachable from inside the container. It is only set if the application was started by the caller.
    __environment_variable_name_of_application_host: str = "VisualRegressionTestsApplicationHost"

    __tfcps_codeunit: TFCPS_CodeUnitSpecific_Base = None
    __sc: ScriptCollectionCore = None

    def __init__(self, tfcps_codeunit: TFCPS_CodeUnitSpecific_Base):
        self.__tfcps_codeunit = tfcps_codeunit
        self.__sc = ScriptCollectionCore()
        self.__sc.log.loglevel = tfcps_codeunit.get_verbosity()

    @GeneralUtilities.check_arguments
    def run(self, update_baselines: bool, playwright_project_folder_relative_path: str = ".", domain_of_externally_started_application: str = None, environment_variables: dict[str, str] = None) -> None:
        """Executes the visual-regression-tests of the codeunit.
        If 'update_baselines' is true then the baseline-screenshots are regenerated instead of being compared.
        'playwright_project_folder_relative_path' is the folder inside the codeunit which contains
        "package.json" and "playwright.config.ts"; it allows codeunits which are not implemented in javascript
        to keep these files out of their sourcecode-folder.
        'domain_of_externally_started_application' has to be set if the caller started the application under test
        instead of letting the playwright-configuration start it (see the documentation of this class). Its value
        is the domain the application is configured for; that domain is made to point to the application inside
        the container and is passed to the testcases as the address they have to use.
        'environment_variables' are passed to the container, which allows the caller to give the testcases
        values which it defines itself, for example the credentials of a user it created."""
        codeunit_folder: str = self.__tfcps_codeunit.get_codeunit_folder()
        repository_folder: str = self.__tfcps_codeunit.get_repository_folder()
        playwright_project_folder: str = self.__get_folder_in_codeunit(codeunit_folder, playwright_project_folder_relative_path)
        image: str = self.__tfcps_codeunit.tfcps_Tools_General.oci_image_manager.get_registry_address_for_image_with_default_tag(repository_folder, self.__image_name)
        self.__assert_version_of_playwright_package_matches_image(playwright_project_folder, image)
        self.__assert_docker_daemon_is_reachable()
        image_address, image_tag = ScriptCollectionCore.split_image_address_and_tag(image)
        self.__sc.docker_pull(image_address, image_tag)
        codeunit_folder_in_container: str = self.__get_codeunit_folder_in_container(codeunit_folder)
        working_folder: str = self.__append_relative_path(codeunit_folder_in_container, playwright_project_folder_relative_path)
        # The output-folder is set here and not only in the playwright-configuration of the codeunit, because the
        # screenshots of failed testcases have to be picked up from that folder afterwards. It is passed as an
        # absolute path because the working-folder is not necessarily the codeunit-folder itself.
        output_folder: str = self.__append_relative_path(codeunit_folder_in_container, self.__test_results_folder_relative_path)
        command: str = f"npx playwright test --output={output_folder}"
        if update_baselines:
            command = f"{command} --update-snapshots"
        # The dependencies are installed inside the container because the "node_modules"-folder of the codeunit can
        # contain packages for another operating-system. "--no-save" is required so that the installation does not
        # modify "package.json" or "package-lock.json".
        command = f"npm install --no-audit --no-fund --no-save && {command}"
        arguments: list[str] = ["run", "--rm"]
        # Playwright recommends this because the default-size of the shared memory of a container is too small for
        # chromium, which makes chromium crash on pages which are not trivial.
        arguments = arguments+["--ipc=host"]
        arguments = arguments+self.__get_mount_arguments(codeunit_folder, codeunit_folder_in_container, playwright_project_folder_relative_path)
        if domain_of_externally_started_application is not None:
            arguments = arguments+self.__get_network_arguments(domain_of_externally_started_application)
        if environment_variables is not None:
            for name, value in environment_variables.items():
                arguments = arguments+["-e", f"{name}={value}"]
        arguments = arguments+["-w", working_folder, image, "/bin/sh", "-c", command]
        result = self.__sc.run_program_argsasarray("docker", arguments, throw_exception_if_exitcode_is_not_zero=False, print_live_output=True, print_errors_as_information=True)
        if result[0] != 0:
            message: str = f"The visual-regression-tests of the codeunit \"{self.__tfcps_codeunit.get_codeunit_name()}\" failed (exit-code {result[0]})."
            folder_with_screenshots: str = self.__preserve_screenshots_of_failed_testcases(codeunit_folder)
            if folder_with_screenshots is None:
                message = f"{message} No screenshots of failed testcases were generated, so probably no testcase was executed at all."
            else:
                message = f"{message} The expected, the actual and the differing screenshot of every failed testcase were stored in \"{folder_with_screenshots}\"."
            message = f"{message} The differences which were found are additionally documented in \"Other/Artifacts/VisualRegressionTestReport\"."
            raise ValueError(message)

    @GeneralUtilities.check_arguments
    def __get_network_arguments(self, domain_of_application: str) -> list[str]:
        """Returns the arguments which make the application under test, which runs outside of the
        playwright-container, reachable from inside it under the domain it is configured for.

        The domain is used and not the ip-address, because a server-side-rendered application puts its own
        configured address into the links and form-actions of every page it delivers. A browser which reached it
        under another address would leave the application as soon as it follows one of them."""
        if self.__is_running_in_container():
            # The application was started by this process, which runs in a container, so it listens on the
            # loopback-interface of that container. Sharing its network-namespace is the only way to reach it:
            # its ports are not published to the host, and publishing them would additionally make two parallel
            # builds on the same host collide with each other.
            address_of_application: str = "127.0.0.1"
            result: list[str] = ["--network", f"container:{self.__get_own_container_id()}"]
        else:
            # The application runs directly on the host of the container, which docker makes reachable under the
            # address "host-gateway".
            address_of_application: str = "host-gateway"
            result: list[str] = []
        return result+["--add-host", f"{domain_of_application}:{address_of_application}", "-e", f"{self.__environment_variable_name_of_application_host}={domain_of_application}"]

    @GeneralUtilities.check_arguments
    def __get_mount_arguments(self, codeunit_folder: str, codeunit_folder_in_container: str, playwright_project_folder_relative_path: str) -> list[str]:
        if self.__is_running_in_container():
            # The build itself runs in a container and uses the docker-daemon of the host. A bind-mount of a path of
            # this container would be resolved by the daemon of the host, where that path does not exist or points to
            # unrelated data. Sharing the own volumes exposes the codeunit to the playwright-container at the same path.
            result: list[str] = ["--volumes-from", self.__get_own_container_id()]
        else:
            result: list[str] = ["-v", f"{codeunit_folder}:{codeunit_folder_in_container}"]
        # The "node_modules"-folder is hidden by an own volume so that the installation inside the container neither
        # uses nor overwrites the packages which were installed outside of the container for another operating-system.
        # The volume is reused by the following runs, so the installation is only slow once.
        volume_name: str = f"{self.__tfcps_codeunit.get_codeunit_name().lower()}-visual-regression-tests-node-modules"
        node_modules_folder: str = self.__append_relative_path(codeunit_folder_in_container, playwright_project_folder_relative_path)+"/node_modules"
        return result+["-v", f"{volume_name}:{node_modules_folder}"]

    @GeneralUtilities.check_arguments
    def __get_codeunit_folder_in_container(self, codeunit_folder: str) -> str:
        if self.__is_running_in_container():
            # The volumes are shared, so the codeunit is available under the path it has in this container.
            return codeunit_folder.replace("\\", "/")
        return self.__codeunit_folder_in_container

    @GeneralUtilities.check_arguments
    def __append_relative_path(self, folder_in_container: str, relative_path: str) -> str:
        # The paths inside the container are always posix-paths, independent of the operating-system this process
        # runs on, so they are composed textually and not by "os.path.join".
        normalized_relative_path: str = relative_path.replace("\\", "/").strip("/")
        if normalized_relative_path in ("", "."):
            return folder_in_container
        return f"{folder_in_container}/{normalized_relative_path}"

    @GeneralUtilities.check_arguments
    def __is_running_in_container(self) -> bool:
        # The filesystem-marker is checked in addition to the convention-based environment-variable because a wrong
        # result here does not only change a message but makes the container access the wrong folder.
        return os.path.exists("/.dockerenv") or self.__sc.is_runnning_in_container()

    @GeneralUtilities.check_arguments
    def __get_own_container_id(self) -> str:
        # Determines the id of the container this process runs in, so that its volumes can be shared with the
        # playwright-container via "docker run --volumes-from".
        # In mountinfo the own container-id only appears reliably in the source-path of the "/etc/hostname"-,
        # "/etc/hosts"- and "/etc/resolv.conf"-mounts, so the "containers/"-prefix has to be matched explicitly: a
        # plain match of 64 hexadecimal characters would also match overlay-layer-hashes, which are not containers.
        try:
            with open("/proc/self/mountinfo", "r", encoding="utf-8") as file_handle:
                match = re.search(r"/containers/([0-9a-f]{64})/", file_handle.read())
                if match is not None:
                    return match.group(1)
        except OSError:
            pass
        # cgroup (v1): the container-id is part of the cgroup-path; here a plain match is safe.
        try:
            with open("/proc/self/cgroup", "r", encoding="utf-8") as file_handle:
                match = re.search(r"[0-9a-f]{64}", file_handle.read())
                if match is not None:
                    return match.group(0)
        except OSError:
            pass
        # Fallback: for a container which was started without an explicit hostname the hostname is the short
        # container-id.
        return socket.gethostname()

    @GeneralUtilities.check_arguments
    def __assert_docker_daemon_is_reachable(self) -> None:
        # Without this check an unreachable daemon would look like a failed testcase, because "docker run" returns a
        # non-zero exit-code in both cases.
        result = self.__sc.run_program_argsasarray("docker", ["version", "--format", "{{.Server.Version}}"], throw_exception_if_exitcode_is_not_zero=False, print_live_output=False)
        if result[0] != 0:
            raise ValueError(f"The visual-regression-tests can not be executed because the docker-daemon is not reachable (exit-code {result[0]}: {result[2].strip()}). The tests are executed via \"docker run\", which requires a running docker-daemon (inside a build-container its socket must be forwarded to the host-daemon). This is an infrastructure-problem and not a failed testcase.")

    @GeneralUtilities.check_arguments
    def __assert_version_of_playwright_package_matches_image(self, playwright_project_folder: str, image: str) -> None:
        image_tag: str = ScriptCollectionCore.split_image_address_and_tag(image)[1]
        match = self.__tag_pattern_with_version_of_playwright.match(image_tag)
        if match is None:
            raise ValueError(f"The tag \"{image_tag}\" of the image \"{self.__image_name}\" does not contain a playwright-version. Expected is a tag like \"v1.62.1-noble\".")
        version_of_image: str = match.group("version")
        with open(os.path.join(playwright_project_folder, "package.json"), "r", encoding="utf-8") as file_handle:
            version_of_package: str = json.load(file_handle)["devDependencies"]["@playwright/test"]
        if version_of_package != version_of_image:
            raise ValueError(f"The version {version_of_package} of the package \"@playwright/test\" does not match the version {version_of_image} of the image \"{self.__image_name}\" (which is defined in \".ScriptCollection/OCIImages/ImageDefinition.csv\"). The image contains the browsers of exactly one playwright-version, so both have to be updated together.")

    @GeneralUtilities.check_arguments
    def __preserve_screenshots_of_failed_testcases(self, codeunit_folder: str) -> str:
        """Copies the screenshots of the failed testcases into an own folder and returns that folder,
        or returns None if there are no such screenshots.
        This is required because playwright empties its output-folder at the beginning of every run, so the
        screenshots of a testcase which fails only sporadically would be lost with the next run."""
        source_folder: str = self.__get_folder_in_codeunit(codeunit_folder, self.__test_results_folder_relative_path)
        if not os.path.isdir(source_folder):
            return None
        # Playwright creates one subfolder per failed testcase. The files which are directly in the output-folder
        # (for example ".last-run.json") do not belong to a specific testcase and are therefore not preserved.
        folders_of_failed_testcases: list[str] = GeneralUtilities.get_direct_folders_of_folder(source_folder)
        if len(folders_of_failed_testcases) == 0:
            return None
        timestamp: str = GeneralUtilities.datetime_to_string_for_logfile_name(GeneralUtilities.get_now(), False)
        target_folder: str = os.path.join(self.__get_folder_in_codeunit(codeunit_folder, self.__failed_testcases_folder_relative_path), timestamp)
        GeneralUtilities.ensure_directory_exists(target_folder)
        for folder_of_failed_testcase in folders_of_failed_testcases:
            GeneralUtilities.copy_content_of_folder(folder_of_failed_testcase, os.path.join(target_folder, os.path.basename(folder_of_failed_testcase)))
        return target_folder

    @GeneralUtilities.check_arguments
    def __get_folder_in_codeunit(self, codeunit_folder: str, relative_path: str) -> str:
        # The relative paths are defined with a slash because they are also passed to the container, so they have to
        # be converted to a path of the operating-system this process runs on.
        return os.path.join(codeunit_folder, *[part for part in relative_path.replace("\\", "/").split("/") if part not in ("", ".")])
