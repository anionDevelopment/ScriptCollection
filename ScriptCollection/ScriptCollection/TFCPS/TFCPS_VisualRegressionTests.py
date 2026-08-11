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

    The used image is defined as "Playwright" in ".ScriptCollection/OCIImages/ImageDefinition.csv" of the
    repository, like the images of all other tools which are used by the build."""

    __image_name: str = "Playwright"

    # The image contains the browsers of exactly one playwright-version, so the version of the
    # "@playwright/test"-package of the codeunit has to be the same one. Otherwise playwright would look for
    # browsers which are not contained in the image.
    __tag_pattern_with_version_of_playwright = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)")

    # The folder the codeunit is mounted to if the tests are started directly on the host.
    __codeunit_folder_in_container: str = "/codeunit"

    __tfcps_codeunit: TFCPS_CodeUnitSpecific_Base = None
    __sc: ScriptCollectionCore = None

    def __init__(self, tfcps_codeunit: TFCPS_CodeUnitSpecific_Base):
        self.__tfcps_codeunit = tfcps_codeunit
        self.__sc = ScriptCollectionCore()
        self.__sc.log.loglevel = tfcps_codeunit.get_verbosity()

    @GeneralUtilities.check_arguments
    def run(self, update_baselines: bool) -> None:
        """Executes the visual-regression-tests of the codeunit.
        If 'update_baselines' is true then the baseline-screenshots are regenerated instead of being compared."""
        codeunit_folder: str = self.__tfcps_codeunit.get_codeunit_folder()
        repository_folder: str = self.__tfcps_codeunit.get_repository_folder()
        image: str = self.__tfcps_codeunit.tfcps_Tools_General.oci_image_manager.get_registry_address_for_image_with_default_tag(repository_folder, self.__image_name)
        self.__assert_version_of_playwright_package_matches_image(codeunit_folder, image)
        self.__assert_docker_daemon_is_reachable()
        image_address, image_tag = ScriptCollectionCore.split_image_address_and_tag(image)
        self.__sc.docker_pull(image_address, image_tag)
        working_folder: str = self.__get_codeunit_folder_in_container(codeunit_folder)
        command: str = "npx playwright test"
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
        arguments = arguments+self.__get_mount_arguments(codeunit_folder, working_folder)
        arguments = arguments+["-w", working_folder, image, "/bin/sh", "-c", command]
        result = self.__sc.run_program_argsasarray("docker", arguments, throw_exception_if_exitcode_is_not_zero=False, print_live_output=True, print_errors_as_information=True)
        if result[0] != 0:
            raise ValueError(f"The visual-regression-tests of the codeunit \"{self.__tfcps_codeunit.get_codeunit_name()}\" failed (exit-code {result[0]}). The differences which were found are documented in \"Other/Artifacts/VisualRegressionTestReport\".")

    @GeneralUtilities.check_arguments
    def __get_mount_arguments(self, codeunit_folder: str, working_folder: str) -> list[str]:
        if self.__is_running_in_container():
            # The build itself runs in a container and uses the docker-daemon of the host. A bind-mount of a path of
            # this container would be resolved by the daemon of the host, where that path does not exist or points to
            # unrelated data. Sharing the own volumes exposes the codeunit to the playwright-container at the same path.
            result: list[str] = ["--volumes-from", self.__get_own_container_id()]
        else:
            result: list[str] = ["-v", f"{codeunit_folder}:{working_folder}"]
        # The "node_modules"-folder is hidden by an own volume so that the installation inside the container neither
        # uses nor overwrites the packages which were installed outside of the container for another operating-system.
        # The volume is reused by the following runs, so the installation is only slow once.
        volume_name: str = f"{self.__tfcps_codeunit.get_codeunit_name().lower()}-visual-regression-tests-node-modules"
        return result+["-v", f"{volume_name}:{working_folder}/node_modules"]

    @GeneralUtilities.check_arguments
    def __get_codeunit_folder_in_container(self, codeunit_folder: str) -> str:
        if self.__is_running_in_container():
            # The volumes are shared, so the codeunit is available under the path it has in this container.
            return codeunit_folder.replace("\\", "/")
        return self.__codeunit_folder_in_container

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
    def __assert_version_of_playwright_package_matches_image(self, codeunit_folder: str, image: str) -> None:
        image_tag: str = ScriptCollectionCore.split_image_address_and_tag(image)[1]
        match = self.__tag_pattern_with_version_of_playwright.match(image_tag)
        if match is None:
            raise ValueError(f"The tag \"{image_tag}\" of the image \"{self.__image_name}\" does not contain a playwright-version. Expected is a tag like \"v1.62.1-noble\".")
        version_of_image: str = match.group("version")
        with open(os.path.join(codeunit_folder, "package.json"), "r", encoding="utf-8") as file_handle:
            version_of_package: str = json.load(file_handle)["devDependencies"]["@playwright/test"]
        if version_of_package != version_of_image:
            raise ValueError(f"The version {version_of_package} of the package \"@playwright/test\" does not match the version {version_of_image} of the image \"{self.__image_name}\" (which is defined in \".ScriptCollection/OCIImages/ImageDefinition.csv\"). The image contains the browsers of exactly one playwright-version, so both have to be updated together.")
