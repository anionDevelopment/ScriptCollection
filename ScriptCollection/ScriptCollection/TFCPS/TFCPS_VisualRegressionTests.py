import json
import os
import re
import socket
from PIL import Image, ImageChops
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

    # The file which maps a domain to an address inside a container. It belongs to the container which owns the
    # network-namespace, so the playwright-container uses the one of this container when it joins it.
    __hosts_file: str = "/etc/hosts"

    # The address the application under test listens on when it was started by this process.
    __loopback_address: str = "127.0.0.1"

    # The folder the screenshots of failed testcases are preserved in. Both folders are located in
    # "Other/Artifacts", which is ignored by git.
    __failed_testcases_folder_relative_path: str = "Other/Artifacts/VisualRegressionTestFailures"

    # The name of the environment-variable which tells the testcases under which hostname the application under
    # test is reachable from inside the container. It is only set if the application was started by the caller.
    __environment_variable_name_of_application_host: str = "VisualRegressionTestsApplicationHost"

    # The folder which contains the baseline-screenshots. Its structure is "<browser>/<platform>/<name>.png",
    # which is the structure the "snapshotPathTemplate" of the playwright-configuration produces.
    __baseline_screenshots_folder_relative_path: str = "Other/Resources/VisualRegressionBaselines"

    # The folder the testcases write the geometry of the pages to, structured as "<browser>/<platform>/<name>.json".
    # It is located in the artifacts-folder because its content is not a baseline which somebody maintains: it only
    # exists for the comparison inside the run which created it.
    __layouts_folder_relative_path: str = "Other/Artifacts/VisualRegressionLayouts"

    __tfcps_codeunit: TFCPS_CodeUnitSpecific_Base = None
    __sc: ScriptCollectionCore = None

    def __init__(self, tfcps_codeunit: TFCPS_CodeUnitSpecific_Base):
        self.__tfcps_codeunit = tfcps_codeunit
        self.__sc = ScriptCollectionCore()
        self.__sc.log.loglevel = tfcps_codeunit.get_verbosity()

    @GeneralUtilities.check_arguments
    def run(self, update_baselines: bool, playwright_project_folder_relative_path: str = ".", domain_of_externally_started_application: str = None, environment_variables: dict[str, str] = None, playwright_project: str = None) -> None:
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
        values which it defines itself, for example the credentials of a user it created.
        'playwright_project' restricts the run to one project of the playwright-configuration (which is one
        browser). It is required by codeunits whose testcases change the state of the application under test:
        those have to start the application newly for every browser, because otherwise the second browser would
        find the state which the first one left behind and would therefore see other pages than the first one."""
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
        self.__remove_layouts_of_previous_run(codeunit_folder, playwright_project)
        command: str = f"npx playwright test --output={output_folder}"
        if playwright_project is not None:
            command = f"{command} --project={playwright_project}"
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
    def __remove_layouts_of_previous_run(self, codeunit_folder: str, playwright_project: str) -> None:
        """Removes the layouts which a previous run wrote, so that a page which does not exist anymore is not
        compared any longer.

        Only the layouts of the browsers which are about to run are removed: a codeunit which executes one browser
        per run would otherwise delete the layouts of the browsers which already ran, and there would never be two
        of them to compare with each other."""
        folder: str = self.__get_folder_in_codeunit(codeunit_folder, self.__layouts_folder_relative_path)
        if playwright_project is not None:
            folder = os.path.join(folder, playwright_project)
        if os.path.isdir(folder):
            GeneralUtilities.ensure_directory_does_not_exist(folder)

    @GeneralUtilities.check_arguments
    def check_screenshots_are_similar(self, maximal_amount_of_different_pixels: int = 400, downscale_factor: int = 8, maximal_difference_per_color_channel: int = 32, baseline_screenshots_folder_relative_path: str = None) -> None:
        """Asserts that the baseline-screenshots of the browsers are roughly the same picture.

        The testcases are written once and are executed by every browser, so every page has one baseline-screenshot
        per browser, and each of them is only ever compared with the screenshot of its own browser. A page which
        looks completely different in one browser therefore stays green forever. This check compares the
        baseline-screenshots of the browsers with each other and thereby detects that.

        It is a coarse check on purpose and it is not the one which detects a misplaced element - use
        'check_layouts_are_similar' for that. Reason: the engines rasterize text differently, so on a page which
        looks the same thousands of pixels differ, and a threshold which tolerates that is too high to detect a
        part of a page which moved. What this check does detect is a picture which is missing, a page which has a
        different height and a page whose content is completely different.

        Every screenshot is compared with the screenshot of the same name and the same platform of every other
        browser which has one; a screenshot which only exists for one browser is skipped.

        'maximal_amount_of_different_pixels' is the amount of pixels two screenshots are allowed to differ in
        (counted after the downscaling, so it is not the amount of pixels of the original screenshot).
        'downscale_factor' says by which factor the screenshots are made smaller before they are compared. The
        downscaling averages the pixels of every block, which is what removes the difference of the
        text-rasterization: it is spread over the whole block and stays below the threshold, while a part of the
        page which really moved keeps differing.
        'maximal_difference_per_color_channel' defines when a pixel counts as different at all.
        'baseline_screenshots_folder_relative_path' allows a codeunit which stores its baseline-screenshots
        somewhere else to say where they are."""
        codeunit_folder: str = self.__tfcps_codeunit.get_codeunit_folder()
        if baseline_screenshots_folder_relative_path is None:
            baseline_screenshots_folder_relative_path = self.__baseline_screenshots_folder_relative_path
        folder: str = self.__get_folder_in_codeunit(codeunit_folder, baseline_screenshots_folder_relative_path)
        if not os.path.isdir(folder):
            raise ValueError(f"The folder with the baseline-screenshots (\"{folder}\") does not exist. The baseline-screenshots have to be generated before they can be compared with each other.")
        screenshots: dict[tuple[str, str], dict[str, str]] = self.__get_files_per_browser(folder, ".png")
        differences: list[str] = []
        for (platform, name), screenshot_per_browser in sorted(screenshots.items()):
            browsers: list[str] = sorted(screenshot_per_browser.keys())
            for index, browser in enumerate(browsers):
                for other_browser in browsers[index+1:]:
                    difference: str = self.__get_difference_of_screenshots(screenshot_per_browser[browser], screenshot_per_browser[other_browser], downscale_factor, maximal_difference_per_color_channel, maximal_amount_of_different_pixels)
                    if difference != "":
                        differences.append(f"{platform}/{name}: the screenshots of {browser} and {other_browser} {difference}.")
        if 0 < len(differences):
            raise ValueError(f"The browsers do not show the same thing. This means the pages themselves look different in different browsers, which the per-browser-baselines do not detect. Details:{os.linesep}{os.linesep.join(differences)}")

    @GeneralUtilities.check_arguments
    def check_layouts_are_similar(self, maximal_difference_in_pixels: int = 12, paths_of_elements_to_ignore: list[str] = None) -> None:
        """Asserts that all browsers laid the pages out the same way.

        This is the check which really answers whether a page looks the same in every browser. Comparing the
        screenshots of the browsers with each other can not answer it: the engines rasterize text differently, so
        even a page which looks identical differs in thousands of pixels, which means the threshold of such a
        comparison has to be so high that it does not detect a shifted part of a page anymore. The geometry of the
        elements does not depend on the rasterization and can therefore be compared directly.

        Compared is what the testcases wrote down while they ran (see the helper "saveLayoutOfPage" of the
        codeunit): the position and the size of every rendered element of every checked page. Every browser is
        compared with every other browser which checked the same page on the same platform.

        'maximal_difference_in_pixels' is how much the position and the size of an element are allowed to differ.
        It is not zero because the engines measure a text slightly differently, so every element whose size comes
        from its own text is a few pixels wider or narrower in one engine than in another; on a headline in a big
        font-size this reaches about ten pixels, which is where the default comes from. A layout-defect (an
        element which lands in the wrong place because an engine treats a css-construct differently) is usually
        far bigger than that.
        'paths_of_elements_to_ignore' excludes elements whose path contains one of the given texts. This is
        required for parts of a page which are not built by the codeunit itself but by a third-party-library
        which renders a different document in different browsers."""
        codeunit_folder: str = self.__tfcps_codeunit.get_codeunit_folder()
        folder: str = self.__get_folder_in_codeunit(codeunit_folder, self.__layouts_folder_relative_path)
        if not os.path.isdir(folder):
            raise ValueError(f"The folder with the layouts of the pages (\"{folder}\") does not exist. The testcases write it while they run, so either they were not executed or they do not save the layout of the pages they check.")
        if paths_of_elements_to_ignore is None:
            paths_of_elements_to_ignore = []
        layouts: dict[tuple[str, str], dict[str, str]] = self.__get_files_per_browser(folder, ".json")
        differences: list[str] = []
        for (platform, name), file_per_browser in sorted(layouts.items()):
            browsers: list[str] = sorted(file_per_browser.keys())
            for index, browser in enumerate(browsers):
                for other_browser in browsers[index+1:]:
                    for difference in self.__get_differences_of_layouts(file_per_browser[browser], file_per_browser[other_browser], maximal_difference_in_pixels, paths_of_elements_to_ignore):
                        differences.append(f"{platform}/{name}: {browser} and {other_browser} {difference}")
        if 0 < len(differences):
            amount_which_is_shown: int = 25
            shown: list[str] = differences[:amount_which_is_shown]
            message: str = f"The browsers do not lay the pages out the same way ({len(differences)} difference(s)). This means the pages themselves look different in different browsers, which the comparison of a screenshot with the baseline of its own browser can not detect."
            if len(shown) < len(differences):
                message = f"{message} The first {amount_which_is_shown} differences:"
            raise ValueError(f"{message}{os.linesep}{os.linesep.join(shown)}")

    @GeneralUtilities.check_arguments
    def __get_differences_of_layouts(self, file: str, other_file: str, maximal_difference_in_pixels: int, paths_of_elements_to_ignore: list[str]) -> list[str]:
        """Returns one description per element which is not at the same place in both given layouts."""
        elements: dict[str, dict] = self.__read_layout(file, paths_of_elements_to_ignore)
        other_elements: dict[str, dict] = self.__read_layout(other_file, paths_of_elements_to_ignore)
        result: list[str] = []
        for path in sorted(set(elements.keys())-set(other_elements.keys())):
            result.append(f"render the element \"{path}\" only in the first one")
        for path in sorted(set(other_elements.keys())-set(elements.keys())):
            result.append(f"render the element \"{path}\" only in the second one")
        for path in sorted(set(elements.keys()) & set(other_elements.keys())):
            element = elements[path]
            other_element = other_elements[path]
            differing_properties: list[str] = []
            for property_name in ["x", "y", "width", "height"]:
                difference: int = abs(element[property_name]-other_element[property_name])
                if maximal_difference_in_pixels < difference:
                    differing_properties.append(f"{property_name} {element[property_name]} vs. {other_element[property_name]}")
            if 0 < len(differing_properties):
                result.append(f"place the element \"{path}\" differently ({', '.join(differing_properties)})")
        return result

    @GeneralUtilities.check_arguments
    def __read_layout(self, file: str, paths_of_elements_to_ignore: list[str]) -> dict[str, dict]:
        with open(file, "r", encoding="utf-8") as file_handle:
            elements: list[dict] = json.load(file_handle)
        return {element["path"]: element for element in elements if not any(ignored in element["path"] for ignored in paths_of_elements_to_ignore)}

    @GeneralUtilities.check_arguments
    def __get_files_per_browser(self, folder: str, extension: str) -> dict[tuple[str, str], dict[str, str]]:
        """Returns the files of a folder which is structured as "<browser>/<platform>/<name><extension>", grouped
        by the platform and the name they have, so that the files which belong to the same page are together."""
        result: dict[tuple[str, str], dict[str, str]] = {}
        for browser_folder in GeneralUtilities.get_direct_folders_of_folder(folder):
            browser: str = os.path.basename(browser_folder)
            for platform_folder in GeneralUtilities.get_direct_folders_of_folder(browser_folder):
                platform: str = os.path.basename(platform_folder)
                for file in GeneralUtilities.get_direct_files_of_folder(platform_folder):
                    if file.lower().endswith(extension):
                        key: tuple[str, str] = (platform, os.path.basename(file))
                        if key not in result:
                            result[key] = {}
                        result[key][browser] = file
        return result

    @GeneralUtilities.check_arguments
    def __get_difference_of_screenshots(self, file: str, other_file: str, downscale_factor: int, maximal_difference_per_color_channel: int, maximal_amount_of_different_pixels: int) -> str:
        """Returns a description of the difference of the two given screenshots, or an empty string when they are
        similar enough."""
        with Image.open(file) as image, Image.open(other_file) as other_image:
            if image.size != other_image.size:
                return f"have different sizes ({image.size[0]}x{image.size[1]} and {other_image.size[0]}x{other_image.size[1]})"
            converted_image: Image.Image = self.__get_downscaled_screenshot(image, downscale_factor)
            converted_other_image: Image.Image = self.__get_downscaled_screenshot(other_image, downscale_factor)
            difference = ImageChops.difference(converted_image, converted_other_image)
            # The difference of a pixel is the biggest difference of its color-channels. The channels are combined
            # with "lighter" (which takes the bigger value of two images) instead of by converting the difference to
            # grayscale, because grayscale weights the channels and would therefore round a small difference which
            # only exists in one channel down to zero.
            red, green, blue = difference.split()
            difference_per_pixel = ImageChops.lighter(ImageChops.lighter(red, green), blue)
            amount_of_different_pixels: int = sum(amount for value, amount in enumerate(difference_per_pixel.histogram()) if maximal_difference_per_color_channel < value)
        if maximal_amount_of_different_pixels < amount_of_different_pixels:
            return f"differ in {amount_of_different_pixels} pixels, which is more than the allowed {maximal_amount_of_different_pixels}"
        return ""

    @GeneralUtilities.check_arguments
    def __get_downscaled_screenshot(self, image: Image.Image, downscale_factor: int) -> Image.Image:
        # The conversion is required because a comparison needs both pictures to have the same amount of channels,
        # and playwright writes a png with or without an alpha-channel depending on the page.
        converted: Image.Image = image.convert("RGB")
        if downscale_factor < 2:
            return converted
        # "BOX" is the filter which builds the average of every block. Another filter would weight the pixels of a
        # block differently, which would keep more of the difference of the text-rasterization.
        return converted.resize((max(1, converted.width//downscale_factor), max(1, converted.height//downscale_factor)), Image.Resampling.BOX)

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
            # The domain can not be passed as "--add-host" in this case: a container which joins the
            # network-namespace of another one uses the hosts-file of that other container and therefore can not
            # have entries of its own, which docker refuses with "conflicting options: custom host-to-IP mapping
            # and the network mode". The mapping is therefore written into the hosts-file of this container, which
            # the playwright-container sees through exactly that sharing.
            self.__ensure_domain_is_mapped_in_the_own_hosts_file(domain_of_application)
            result: list[str] = ["--network", f"container:{self.__get_own_container_id()}"]
        else:
            # The application runs directly on the host of the container, which docker makes reachable under the
            # address "host-gateway". The playwright-container has a hosts-file of its own in this case, so the
            # mapping can be passed as an argument.
            result: list[str] = ["--add-host", f"{domain_of_application}:host-gateway"]
        return result+["-e", f"{self.__environment_variable_name_of_application_host}={domain_of_application}"]

    @GeneralUtilities.check_arguments
    def __ensure_domain_is_mapped_in_the_own_hosts_file(self, domain_of_application: str) -> None:
        """Maps the given domain to the loopback-interface in the hosts-file of the container this process runs in.

        The playwright-container joins the network-namespace of this container and therefore uses its hosts-file, so
        this is the only place where the mapping can be put for the browser to resolve the domain.
        The mapping is appended instead of the file being rewritten, because the file is a bind-mount of the
        docker-daemon (which is also how __get_own_container_id recognizes the own container): replacing it would
        break that mount and the mapping would not reach the playwright-container.
        A mapping which is already there is not appended a second time, so that the runs for the further browsers of
        the codeunit do not add it again."""
        for line in GeneralUtilities.read_text_from_file(self.__hosts_file).splitlines():
            # Everything behind a "#" is a comment, and a line maps its first field (the address) to all further
            # fields (the names it is reachable under).
            fields: list[str] = line.split("#", 1)[0].split()
            if 1 < len(fields) and fields[0] == self.__loopback_address and domain_of_application in fields[1:]:
                return
        GeneralUtilities.append_line_to_file(self.__hosts_file, f"{self.__loopback_address}\t{domain_of_application}")

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
