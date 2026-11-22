import os
import re
import base64
import binascii
import zipfile
import shlex
import shutil
import requests
from lxml import etree
from ...GeneralUtilities import GeneralUtilities, Dependency
from ...SCLog import LogLevel
from ..TFCPS_CodeUnitSpecific_Base import TFCPS_CodeUnitSpecific_Base, TFCPS_CodeUnitSpecific_Base_CLI
from ..TFCPS_RemoteBuild import RunnerOperatingSystem


class TFCPS_CodeUnitSpecific_Android_Functions(TFCPS_CodeUnitSpecific_Base):
    """Implements the tasks of a codeunit which contains a native android-app (java or kotlin) built with gradle.

    The gradle-project is expected in "<codeunit>/<codeunit>" as a single-module-project: its "build.gradle" applies the
    android-application-plugin itself and its testcases are located in its own "src/test"-folder, because that is the
    layout gradle defines and the layout the coverage-report of the android-gradle-plugin measures without further
    configuration. The project has to contain the gradle-wrapper ("gradlew" and "gradle/wrapper"), so the gradle-version
    is pinned by the repository and not by the machine which builds it.

    Every gradle-task of the project needs the android-sdk. It is therefore always run on an android-task-runner (see
    SCTaskRunnerAndroid and the remote-build-article in the reference), analogous to the android-target of a
    flutter-codeunit: the android-sdk is not part of SCBuilder.

    Requirements for the "build.gradle" of the project:
    - It declares exactly one "versionCode" and exactly one "versionName" (they are set by do_common_tasks).
    - The debug-build-type sets "enableUnitTestCoverage = true", so the task "createDebugUnitTestCoverageReport" exists.
    - It applies the plugin "org.cyclonedx.bom" and lets the task "cyclonedxBom" write its xml-output to
      "build/outputs/bom/bom.xml" (see get_bom_file_relative_to_build_folder), because only the "build/outputs"-folder is
      transferred back from the runner by the build.
    - Only if the codeunit has visual-regression-tests (see run_visual_regression_tests): it applies the plugin
      "io.github.takahirom.roborazzi" and configures "roborazzi { outputDir = file('../Other/Resources/VisualRegressionBaselines');
      compare { outputDir = layout.buildDirectory.dir('outputs/roborazzi-comparison') } }" (see
      get_visual_regression_baselines_folder and get_visual_regression_comparison_folder_relative_to_build_folder).
    - The release-build-type is signed with the upload-key if the environment-variables "SC_ANDROID_SIGNING_STORE_FILE",
      "SC_ANDROID_SIGNING_STORE_PASSWORD", "SC_ANDROID_SIGNING_KEY_ALIAS" and "SC_ANDROID_SIGNING_KEY_PASSWORD" are set,
      and with the debug-key otherwise (see build), for example:
      "signingConfigs { release { if (System.getenv('SC_ANDROID_SIGNING_STORE_FILE') != null) { storeFile =
      file(System.getenv('SC_ANDROID_SIGNING_STORE_FILE')); storePassword = System.getenv('SC_ANDROID_SIGNING_STORE_PASSWORD');
      keyAlias = System.getenv('SC_ANDROID_SIGNING_KEY_ALIAS'); keyPassword = System.getenv('SC_ANDROID_SIGNING_KEY_PASSWORD') } } }"
      and "release { signingConfig = System.getenv('SC_ANDROID_SIGNING_STORE_FILE') != null ? signingConfigs.release :
      signingConfigs.debug }"."""

    # The environment-variables (of the machine which runs the build, for example the build-pipeline) which contain the
    # upload-key of a productive build, mapped to the environment-variables of the gradle-run on the runner which
    # receive them (see build). The keystore is given as the base64-encoding of the keystore-file, because an
    # environment-variable can not contain a file.
    __signing_environment_variables: dict[str, str] = {
        "Android_Signing_Keystore": "SC_ANDROID_SIGNING_KEYSTORE_BASE64",
        "Android_Signing_StorePassword": "SC_ANDROID_SIGNING_STORE_PASSWORD",
        "Android_Signing_KeyAlias": "SC_ANDROID_SIGNING_KEY_ALIAS",
        "Android_Signing_KeyPassword": "SC_ANDROID_SIGNING_KEY_PASSWORD",
    }

    # The name the subject of the debug-certificate of the android-sdk contains ("CN=Android Debug,O=Android,C=US").
    __subject_of_the_debug_certificate: bytes = b"Android Debug"

    # The repositories in which a dependency or a gradle-plugin of an android-app is published. Gradle itself searches
    # all of them (they are the repositories a project declares by "google()", "mavenCentral()" and
    # "gradlePluginPortal()"), so a dependency can be located in any of them.
    __maven_repositories: list[str] = ["https://dl.google.com/dl/android/maven2", "https://repo1.maven.org/maven2", "https://plugins.gradle.org/m2"]

    # A dependency in the format "<group-id>:<artifact-id>:<version>" inside a string-literal of the build-file.
    __dependency_pattern = re.compile(r"""(?P<quote>['"])(?P<group>[A-Za-z0-9_.\-]+):(?P<artifact>[A-Za-z0-9_.\-]+):(?P<version>[A-Za-z0-9_.\-+]+)(?P=quote)""")

    # A plugin which is declared with its version in the plugins-block of the build-file, for example
    # "id 'com.android.application' version '9.1.0'".
    __plugin_pattern = re.compile(r"""id\s*\(?\s*(?P<quote1>['"])(?P<id>[A-Za-z0-9_.\-]+)(?P=quote1)\s*\)?\s*version\s*\(?\s*(?P<quote2>['"])(?P<version>[A-Za-z0-9_.\-+]+)(?P=quote2)""")

    # The folder of the codeunit which contains the baseline-images of the visual-regression-tests. It is the same
    # folder the visual-regression-tests of the other codeunit-types use (see TFCPS_VisualRegressionTests).
    __visual_regression_baselines_folder_relative_to_codeunit: str = "Other/Resources/VisualRegressionBaselines"

    # The folder the screenshots of failed visual-regression-tests (the actual image and the comparison-image) are
    # preserved in. It is the same folder the visual-regression-tests of the other codeunit-types use.
    __visual_regression_failures_folder_relative_to_codeunit: str = "Other/Artifacts/VisualRegressionTestFailures"

    # The file (inside the comparison-folder) the exit-code of the verifying gradle-run is written to on the runner.
    __exit_code_file_name: str = "GradleExitCode.txt"

    __version_code_pattern = re.compile(r"(?P<prefix>\bversionCode\s*=?\s*)(?P<value>\d+)")
    __version_name_pattern = re.compile(r"""(?P<prefix>\bversionName\s*=?\s*)(?P<quote>['"])(?P<value>[^'"]*)(?P=quote)""")

    def __init__(self, current_file: str, verbosity: LogLevel, targetenvironmenttype: str, use_cache: bool, is_pre_merge: bool):
        super().__init__(current_file, verbosity, targetenvironmenttype, use_cache, is_pre_merge)

    @GeneralUtilities.check_arguments
    def get_gradle_project_folder(self) -> str:
        """Returns the folder which contains the build-file of this codeunit."""
        return os.path.join(self.get_codeunit_folder(), self.get_codeunit_name())

    @GeneralUtilities.check_arguments
    def get_build_file(self) -> str:
        return os.path.join(self.get_gradle_project_folder(), "build.gradle")

    @GeneralUtilities.check_arguments
    def get_build_folder(self) -> str:
        return os.path.join(self.get_gradle_project_folder(), "build")

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_bom_file_relative_to_build_folder() -> str:
        return "outputs/bom/bom.xml"

    @GeneralUtilities.check_arguments
    def get_visual_regression_baselines_folder(self) -> str:
        return os.path.join(self.get_codeunit_folder(), TFCPS_CodeUnitSpecific_Android_Functions.__visual_regression_baselines_folder_relative_to_codeunit)

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_visual_regression_comparison_folder_relative_to_build_folder() -> str:
        return "outputs/roborazzi-comparison"

    @GeneralUtilities.check_arguments
    def build(self) -> None:
        """Builds the app-bundle (which is what is uploaded to a store) and the apk (which can be installed directly) of the
        release-build-type and generates the bill-of-materials. All of them are generated by one gradle-run, so the runner
        has to be used only once for them.

        A productive build (target-environment-type "Productive") is signed with the upload-key, so its app-bundle can be
        uploaded to Google Play. The upload-key is taken from the environment-variables "Android_Signing_Keystore" (the
        base64-encoding of the keystore-file), "Android_Signing_StorePassword", "Android_Signing_KeyAlias" and
        "Android_Signing_KeyPassword", which are required for a productive build. They are given to the gradle-run on the
        runner as environment-variables only (see TFCPS_RemoteBuild.run_program_on_runner); on the runner the keystore
        is written into a temporary file outside of the workspace which is removed when gradle ends. Afterwards it is
        verified that the app-bundle is signed, but not with the debug-key.
        Every other build is signed with the debug-key of the runner, so a developer can build and install the app
        without the upload-key."""
        codeunit_name = self.get_codeunit_name()
        codeunit_version: str = self.tfcps_Tools_General.get_version_of_codeunit(self.get_codeunit_file())
        outputs_folder = os.path.join(self.get_build_folder(), "outputs")
        GeneralUtilities.ensure_directory_does_not_exist(outputs_folder)
        gradle_tasks = ["bundleRelease", "assembleRelease", "cyclonedxBom"]
        is_signed_with_upload_key = self.get_target_environment_type() == "Productive"
        if is_signed_with_upload_key:
            self._protected_sc.log.log("Build the release-build signed with the upload-key...")
            signing_environment_variables = TFCPS_CodeUnitSpecific_Android_Functions.get_signing_environment_variables_for_runner(dict(os.environ))
            script = TFCPS_CodeUnitSpecific_Android_Functions.get_script_which_signs_with_upload_key(self.__get_gradle_arguments(gradle_tasks))
            self.run_program_on_remote_runner(RunnerOperatingSystem.Android, "bash", ["-c", script], self.get_gradle_project_folder(), outputs_folder, self.__get_folders_which_are_not_transferred(), signing_environment_variables)
        else:
            self._protected_sc.log.log(f'Build the release-build signed with the debug-key of the runner (only a build with target-environment-type "Productive" is signed with the upload-key, this one has "{self.get_target_environment_type()}")...')
            self.__run_gradle_on_runner(gradle_tasks, outputs_folder)

        aab_folder = os.path.join(self.get_artifacts_folder(), "BuildResult_AAB")
        GeneralUtilities.ensure_folder_exists_and_is_empty(aab_folder)
        aab_file_original = self._protected_sc.find_file_by_extension(os.path.join(outputs_folder, "bundle", "release"), "aab")
        if is_signed_with_upload_key:
            GeneralUtilities.assert_condition(TFCPS_CodeUnitSpecific_Android_Functions.is_signed(aab_file_original), f'The app-bundle "{aab_file_original}" is not signed. The release-build-type of "{self.get_build_file()}" has to use the upload-key which is given by the environment-variables "SC_ANDROID_SIGNING_*" (see the docstring of TFCPS_CodeUnitSpecific_Android_Functions).')
            GeneralUtilities.assert_condition(not TFCPS_CodeUnitSpecific_Android_Functions.is_signed_with_debug_key(aab_file_original), f'The app-bundle "{aab_file_original}" is signed with the debug-key, so Google Play would reject it. The release-build-type of "{self.get_build_file()}" has to use the upload-key which is given by the environment-variables "SC_ANDROID_SIGNING_*" (see the docstring of TFCPS_CodeUnitSpecific_Android_Functions).')
        shutil.copyfile(aab_file_original, os.path.join(aab_folder, f"{codeunit_name}.aab"))

        apk_folder = os.path.join(self.get_artifacts_folder(), "BuildResult_APK")
        GeneralUtilities.ensure_folder_exists_and_is_empty(apk_folder)
        apk_file_original = self._protected_sc.find_file_by_extension(os.path.join(outputs_folder, "apk", "release"), "apk")
        shutil.copyfile(apk_file_original, os.path.join(apk_folder, f"{codeunit_name}_v{codeunit_version}.apk"))

        bom_folder = os.path.join(self.get_artifacts_folder(), "BOM")
        GeneralUtilities.ensure_directory_exists(bom_folder)
        generated_bom_file = os.path.join(self.get_build_folder(), TFCPS_CodeUnitSpecific_Android_Functions.get_bom_file_relative_to_build_folder())
        GeneralUtilities.assert_file_exists(generated_bom_file)
        target_bom_file = os.path.join(bom_folder, f"{codeunit_name}.{codeunit_version}.bom.xml")
        shutil.copyfile(generated_bom_file, target_bom_file)
        self._protected_sc.format_xml_file(target_bom_file)

        self.copy_source_files_to_output_directory()

    @GeneralUtilities.check_arguments
    def linting(self) -> None:
        self._protected_sc.normalize_invisible_characters_of_files_in_folder(self.get_codeunit_folder(), ["java", "kt"])
        # The rules of android-lint (for example whether a warning lets the linting fail) are configured in the "lint"-block
        # of the build-file, so that the ruleset belongs to the codeunit and not to this implementation.
        reports_folder = os.path.join(self.get_build_folder(), "reports")
        GeneralUtilities.ensure_directory_does_not_exist(reports_folder)
        self.__run_gradle_on_runner(["lintDebug"], reports_folder)

    @GeneralUtilities.check_arguments
    def do_common_tasks(self, current_codeunit_version: str) -> None:
        self.do_common_tasks_base(current_codeunit_version)
        self.__set_version_in_build_file(self.get_version_of_project())

    @GeneralUtilities.check_arguments
    def generate_reference(self) -> None:
        self.generate_reference_using_docfx()

    @GeneralUtilities.check_arguments
    def run_testcases(self) -> None:
        codeunit_name = self.get_codeunit_name()
        reports_folder = os.path.join(self.get_build_folder(), "reports")
        GeneralUtilities.ensure_directory_does_not_exist(reports_folder)
        # "createDebugUnitTestCoverageReport" depends on "testDebugUnitTest", so this runs the testcases and writes the
        # jacoco-report of their coverage.
        self.__run_gradle_on_runner(["createDebugUnitTestCoverageReport"], reports_folder)
        jacoco_file = os.path.join(reports_folder, "coverage", "test", "debug", "report.xml")
        coverage_file = os.path.join(self.get_artifacts_folder(), "TestCoverage", "TestCoverage.xml")
        GeneralUtilities.ensure_file_does_not_exist(coverage_file)
        self.tfcps_Tools_General.convert_jacoco_report_to_cobertura_report(jacoco_file, coverage_file, codeunit_name, self.get_codeunit_folder(), [f"{codeunit_name}/src/main/java", f"{codeunit_name}/src/main/kotlin"])
        self.run_testcases_common_post_task(self.get_repository_folder(), codeunit_name, True, self.get_target_environment_type())

    @GeneralUtilities.check_arguments
    def run_visual_regression_tests(self, update_baselines: bool) -> None:
        """Runs the visual-regression-tests of the app, which are the unit-tests that capture screenshots with roborazzi
        (rendered by robolectric). They run on the android-task-runner like every other gradle-task of the project, so
        the baseline-images are always generated and compared in the same, fixed environment, regardless of whether the
        build runs on a developer-machine or in the build-pipeline: a screenshot depends on the environment which
        renders it.

        If 'update_baselines' is true, the baseline-images in "Other/Resources/VisualRegressionBaselines" are
        (re-)generated ("recordRoborazziDebug"); the folder is emptied before, so the baseline-image of a removed
        screenshot does not remain. Otherwise the screenshots are compared against them ("verifyRoborazziDebug"); if a
        comparison fails, the actual images and the comparison-images are preserved in
        "Other/Artifacts/VisualRegressionTestFailures" and an exception is raised.

        In a normal run of the unit-tests (see run_testcases) the screenshot-testcases run as well, but roborazzi does
        neither record nor compare anything there."""
        baselines_folder = self.get_visual_regression_baselines_folder()
        if update_baselines:
            GeneralUtilities.ensure_folder_exists_and_is_empty(baselines_folder)
            self.__run_gradle_on_runner(["recordRoborazziDebug"], baselines_folder)
            GeneralUtilities.assert_condition(0 < len(TFCPS_CodeUnitSpecific_Android_Functions.__get_png_files(baselines_folder)), f'Recording the visual-regression-baselines did not produce any image in "{baselines_folder}".')
        else:
            GeneralUtilities.assert_condition(0 < len(TFCPS_CodeUnitSpecific_Android_Functions.__get_png_files(baselines_folder)), f'There are no visual-regression-baselines in "{baselines_folder}". Generate them using "Other/QualityCheck/UpdateVisualRegressionBaselines.py".')
            comparison_folder = os.path.join(self.get_build_folder(), TFCPS_CodeUnitSpecific_Android_Functions.get_visual_regression_comparison_folder_relative_to_build_folder())
            GeneralUtilities.ensure_directory_does_not_exist(comparison_folder)
            exit_code = self.__run_gradle_on_runner_and_get_exit_code(["verifyRoborazziDebug"], comparison_folder)
            if exit_code != 0:
                failures_folder = os.path.join(self.get_codeunit_folder(), TFCPS_CodeUnitSpecific_Android_Functions.__visual_regression_failures_folder_relative_to_codeunit)
                GeneralUtilities.ensure_folder_exists_and_is_empty(failures_folder)
                for image in TFCPS_CodeUnitSpecific_Android_Functions.__get_png_files(comparison_folder):
                    shutil.copyfile(image, os.path.join(failures_folder, os.path.basename(image)))
                raise ValueError(f'The visual-regression-tests of the codeunit "{self.get_codeunit_name()}" failed (gradle exit-code {exit_code}). See the runner-log above for details. The screenshots of the failed comparisons are located in "{failures_folder}". If the change of the user-interface is intended, update the baselines using "Other/QualityCheck/UpdateVisualRegressionBaselines.py".')

    @staticmethod
    @GeneralUtilities.check_arguments
    def __get_png_files(folder: str) -> list[str]:
        if not os.path.isdir(folder):
            return []
        return [file for file in GeneralUtilities.get_direct_files_of_folder(folder) if file.lower().endswith(".png")]

    @GeneralUtilities.check_arguments
    def __get_gradle_arguments(self, tasks: list[str]) -> list[str]:
        # "bash gradlew" instead of "./gradlew": the executable-bit of the wrapper-script does not survive a checkout on
        # windows, from where the repository is transferred to the runner.
        result: list[str] = ["gradlew", "--console=plain", "--no-daemon"]+tasks
        if self.get_verbosity() == LogLevel.Debug:
            result.append("--info")
        return result

    @GeneralUtilities.check_arguments
    def __get_folders_which_are_not_transferred(self) -> list[str]:
        # These are generated for the machine they were generated on: "build" and ".gradle" contain absolute paths and
        # caches of that machine, and "local.properties" states the folder of the android-sdk of that machine (it is
        # written by android-studio). On the runner they would describe folders which do not exist there.
        gradle_project_folder = self.get_gradle_project_folder()
        return [os.path.join(gradle_project_folder, "build"), os.path.join(gradle_project_folder, ".gradle"), os.path.join(gradle_project_folder, "local.properties")]

    @GeneralUtilities.check_arguments
    def __run_gradle_on_runner(self, tasks: list[str], result_folder: str) -> None:
        """Runs the given gradle-tasks on an android-task-runner and writes the content of result_folder (which must be a
        folder inside this codeunit) back into this codeunit. A failure of gradle raises an exception."""
        self.run_program_on_remote_runner(RunnerOperatingSystem.Android, "bash", self.__get_gradle_arguments(tasks), self.get_gradle_project_folder(), result_folder, self.__get_folders_which_are_not_transferred(), {})

    @GeneralUtilities.check_arguments
    def __run_gradle_on_runner_and_get_exit_code(self, tasks: list[str], result_folder: str) -> int:
        """Like __run_gradle_on_runner, but a failure of gradle does not raise an exception: its exit-code is returned
        instead. This is required when the result-folder is needed exactly when gradle fails (for example the
        screenshots of failed visual-regression-tests), because the runner returns the result-folder only for a job
        which succeeded. The exit-code is therefore written into the result-folder and the job itself always
        succeeds."""
        result_folder_relative_to_project = os.path.relpath(result_folder, self.get_gradle_project_folder()).replace("\\", "/")
        script = TFCPS_CodeUnitSpecific_Android_Functions.get_script_which_preserves_exit_code(self.__get_gradle_arguments(tasks), result_folder_relative_to_project, TFCPS_CodeUnitSpecific_Android_Functions.__exit_code_file_name)
        self.run_program_on_remote_runner(RunnerOperatingSystem.Android, "bash", ["-c", script], self.get_gradle_project_folder(), result_folder, self.__get_folders_which_are_not_transferred(), {})
        local_exit_code_file = os.path.join(result_folder, TFCPS_CodeUnitSpecific_Android_Functions.__exit_code_file_name)
        GeneralUtilities.assert_file_exists(local_exit_code_file)
        return int(GeneralUtilities.read_text_from_file(local_exit_code_file).strip())

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_signing_environment_variables_for_runner(environment: dict[str, str]) -> dict[str, str]:
        """Returns the environment-variables which give the upload-key to the gradle-run on the runner, taken from the
        given environment-variables of this machine (see build). The names are compared case-insensitively, because
        Windows exposes the names of environment-variables upper-cased via os.environ."""
        environment_upper = {name.upper(): value for name, value in environment.items()}
        missing_variables = [name for name in TFCPS_CodeUnitSpecific_Android_Functions.__signing_environment_variables if len((environment_upper.get(name.upper()) or GeneralUtilities.empty_string).strip()) == 0]
        GeneralUtilities.assert_condition(len(missing_variables) == 0, f'A productive build of an android-app is signed with the upload-key, which requires the environment-variable(s) {", ".join(missing_variables)}. "Android_Signing_Keystore" contains the base64-encoding of the keystore-file.')
        result: dict[str, str] = {}
        for name, name_on_runner in TFCPS_CodeUnitSpecific_Android_Functions.__signing_environment_variables.items():
            result[name_on_runner] = environment_upper[name.upper()]
        # A base64-encoding is often wrapped into several lines (for example by the base64-tool), which is not part of it.
        keystore_base64 = "".join(result["SC_ANDROID_SIGNING_KEYSTORE_BASE64"].split())
        try:
            base64.b64decode(keystore_base64, validate=True)
        except binascii.Error as exception:
            raise ValueError('The environment-variable "Android_Signing_Keystore" does not contain a valid base64-encoding of the keystore-file.') from exception
        result["SC_ANDROID_SIGNING_KEYSTORE_BASE64"] = keystore_base64
        return result

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_script_which_signs_with_upload_key(gradle_arguments: list[str]) -> str:
        """Returns the bash-script which runs gradle on the runner with the upload-key: it writes the keystore (which it
        gets base64-encoded in an environment-variable) into a temporary file outside of the workspace of the job, gives
        that file to gradle via "SC_ANDROID_SIGNING_STORE_FILE" and removes it when the script ends, regardless of how it
        ends."""
        return "set -e; " \
            + 'keystore_file="$(mktemp)"; ' \
            + """trap 'rm -f "$keystore_file"' EXIT; """ \
            + """printf '%s' "$SC_ANDROID_SIGNING_KEYSTORE_BASE64" | base64 -d > "$keystore_file"; """ \
            + "unset SC_ANDROID_SIGNING_KEYSTORE_BASE64; " \
            + 'export SC_ANDROID_SIGNING_STORE_FILE="$keystore_file"; ' \
            + "bash " + shlex.join(gradle_arguments)

    @staticmethod
    @GeneralUtilities.check_arguments
    def __get_signature_blocks(signed_file: str) -> list[bytes]:
        """Returns the signature-blocks of a jar-signed file (an app-bundle is jar-signed): the files "META-INF/*.RSA",
        "META-INF/*.DSA" and "META-INF/*.EC", which contain the certificate of the signer."""
        with zipfile.ZipFile(signed_file) as archive:
            return [archive.read(name) for name in archive.namelist() if re.fullmatch(r"META-INF/[^/]+\.(RSA|DSA|EC)", name, re.IGNORECASE)]

    @staticmethod
    @GeneralUtilities.check_arguments
    def is_signed(signed_file: str) -> bool:
        """Whether the given app-bundle is signed."""
        return len(TFCPS_CodeUnitSpecific_Android_Functions.__get_signature_blocks(signed_file)) > 0

    @staticmethod
    @GeneralUtilities.check_arguments
    def is_signed_with_debug_key(signed_file: str) -> bool:
        """Whether the given app-bundle is signed with the debug-key of an android-sdk. The certificate of that key is
        always issued to "CN=Android Debug,O=Android,C=US", whose name is contained in the signature-block as text."""
        return any(TFCPS_CodeUnitSpecific_Android_Functions.__subject_of_the_debug_certificate in block for block in TFCPS_CodeUnitSpecific_Android_Functions.__get_signature_blocks(signed_file))

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_script_which_preserves_exit_code(gradle_arguments: list[str], result_folder_relative_to_project: str, exit_code_file_name: str) -> str:
        """Returns the bash-script which runs gradle with the given arguments and writes its exit-code into the given
        file inside the given folder instead of failing."""
        exit_code_file = f"{result_folder_relative_to_project}/{exit_code_file_name}"
        return f"mkdir -p {shlex.quote(result_folder_relative_to_project)}; bash {shlex.join(gradle_arguments)}; echo $? > {shlex.quote(exit_code_file)}"

    @GeneralUtilities.check_arguments
    def __set_version_in_build_file(self, new_version: str) -> None:
        build_file = self.get_build_file()
        content = GeneralUtilities.read_text_from_file(build_file)
        content = TFCPS_CodeUnitSpecific_Android_Functions.set_version_in_build_file_content(content, new_version)
        GeneralUtilities.write_text_to_file(build_file, content)

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_version_code(version: str) -> int:
        """Returns the versionCode for the given version. Android requires that the versionCode of an update is greater
        than the one of the installed app, so it is derived from the version: every part of the version gets 3 digits."""
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version)
        GeneralUtilities.assert_condition(match is not None, f'"{version}" is not a version in the format "<major>.<minor>.<patch>".')
        major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))
        GeneralUtilities.assert_condition(minor < 1000 and patch < 1000, f'The minor- and the patch-part of the version "{version}" must be less than 1000 to be representable as versionCode.')
        result = major*1000000+minor*1000+patch
        # 2100000000 is the greatest versionCode google-play accepts.
        GeneralUtilities.assert_condition(result <= 2100000000, f'The version "{version}" is too large to be representable as versionCode.')
        return result

    @staticmethod
    @GeneralUtilities.check_arguments
    def set_version_in_build_file_content(content: str, new_version: str) -> str:
        GeneralUtilities.assert_condition(len(TFCPS_CodeUnitSpecific_Android_Functions.__version_code_pattern.findall(content)) == 1, "The build-file must contain exactly one versionCode.")
        GeneralUtilities.assert_condition(len(TFCPS_CodeUnitSpecific_Android_Functions.__version_name_pattern.findall(content)) == 1, "The build-file must contain exactly one versionName.")
        version_code = TFCPS_CodeUnitSpecific_Android_Functions.get_version_code(new_version)
        content = TFCPS_CodeUnitSpecific_Android_Functions.__version_code_pattern.sub(lambda match: f"{match.group('prefix')}{version_code}", content)
        content = TFCPS_CodeUnitSpecific_Android_Functions.__version_name_pattern.sub(lambda match: f"{match.group('prefix')}{match.group('quote')}{new_version}{match.group('quote')}", content)
        return content

    @GeneralUtilities.check_arguments
    def get_dependencies(self) -> dict[str, set[str]]:
        return GeneralUtilities.merge_dependency_lists([TFCPS_CodeUnitSpecific_Android_Functions.get_dependencies_from_build_file_content(GeneralUtilities.read_text_from_file(self.get_build_file()))])

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_dependencies_from_build_file_content(content: str) -> list[Dependency]:
        """Returns the dependencies ("<group-id>:<artifact-id>") and the plugins ("<plugin-id>") which are declared with an
        explicit version in the given content of a build-file."""
        result: list[Dependency] = []
        for match in TFCPS_CodeUnitSpecific_Android_Functions.__dependency_pattern.finditer(content):
            result.append(Dependency(f"{match.group('group')}:{match.group('artifact')}", match.group("version")))
        for match in TFCPS_CodeUnitSpecific_Android_Functions.__plugin_pattern.finditer(content):
            result.append(Dependency(match.group("id"), match.group("version")))
        return result

    @GeneralUtilities.check_arguments
    def get_available_versions(self, dependencyname: str) -> list[str]:
        return list(self.__get_released_versions(dependencyname).keys())

    @GeneralUtilities.check_arguments
    def __get_released_versions(self, dependencyname: str) -> dict[str, str]:
        """Returns the released versions of the given dependency as dictionary from the version in the format
        "<major>.<minor>.<patch>" (which the update-mechanism requires) to the version as it is published (for example
        "4.18" for a dependency which omits the patch-part)."""
        group_id, artifact_id = TFCPS_CodeUnitSpecific_Android_Functions.get_group_and_artifact_of_dependency(dependencyname)
        found_in_any_repository: bool = False
        result: dict[str, str] = {}
        for repository in TFCPS_CodeUnitSpecific_Android_Functions.__maven_repositories:
            metadata_address = f"{repository}/{group_id.replace('.', '/')}/{artifact_id}/maven-metadata.xml"
            response = requests.get(metadata_address, timeout=60)
            if response.status_code == 404:
                continue
            response.raise_for_status()
            found_in_any_repository = True
            for found_version in etree.fromstring(response.content).xpath("/metadata/versioning/versions/version/text()"):
                normalized_version = TFCPS_CodeUnitSpecific_Android_Functions.normalize_released_version(str(found_version))
                if normalized_version is not None:
                    result[normalized_version] = str(found_version)
        GeneralUtilities.assert_condition(found_in_any_repository, f'The dependency "{dependencyname}" was not found in any of the repositories {", ".join(TFCPS_CodeUnitSpecific_Android_Functions.__maven_repositories)}.')
        return result

    @staticmethod
    @GeneralUtilities.check_arguments
    def normalize_released_version(version: str) -> str:
        """Returns the given version in the format "<major>.<minor>.<patch>", or None if it is not the version of a release
        (for example "1.2.0-alpha01")."""
        if re.match(r"^(\d+)\.(\d+)\.(\d+)$", version) is not None:
            return version
        if re.match(r"^(\d+)\.(\d+)$", version) is not None:
            return version+".0"
        return None

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_group_and_artifact_of_dependency(dependencyname: str) -> tuple[str, str]:
        """A dependency is identified by "<group-id>:<artifact-id>". A plugin is identified by its plugin-id, and gradle
        resolves it through its marker-artifact "<plugin-id>:<plugin-id>.gradle.plugin"."""
        parts = dependencyname.split(":")
        if len(parts) == 1:
            return (dependencyname, f"{dependencyname}.gradle.plugin")
        GeneralUtilities.assert_condition(len(parts) == 2, f'The name of a dependency must have the format "<group-id>:<artifact-id>" or "<plugin-id>" but was "{dependencyname}".')
        return (parts[0], parts[1])

    @GeneralUtilities.check_arguments
    def set_dependency_version(self, name: str, new_version: str) -> None:
        build_file = self.get_build_file()
        content = GeneralUtilities.read_text_from_file(build_file)
        # The version is written in the format in which it is published, because that is the only one gradle can resolve.
        published_version = self.__get_released_versions(name)[new_version]
        content = TFCPS_CodeUnitSpecific_Android_Functions.set_dependency_version_in_build_file_content(content, name, published_version)
        GeneralUtilities.write_text_to_file(build_file, content)

    @staticmethod
    @GeneralUtilities.check_arguments
    def set_dependency_version_in_build_file_content(content: str, name: str, new_version: str) -> str:
        if ":" in name:
            group_id, artifact_id = TFCPS_CodeUnitSpecific_Android_Functions.get_group_and_artifact_of_dependency(name)

            def replace_dependency(match: re.Match) -> str:
                if match.group("group") == group_id and match.group("artifact") == artifact_id:
                    return f"{match.group('quote')}{group_id}:{artifact_id}:{new_version}{match.group('quote')}"
                return match.group(0)
            return TFCPS_CodeUnitSpecific_Android_Functions.__dependency_pattern.sub(replace_dependency, content)
        else:
            def replace_plugin(match: re.Match) -> str:
                if match.group("id") == name:
                    version_start = match.start("version")-match.start(0)
                    version_end = match.end("version")-match.start(0)
                    return match.group(0)[:version_start]+new_version+match.group(0)[version_end:]
                return match.group(0)
            return TFCPS_CodeUnitSpecific_Android_Functions.__plugin_pattern.sub(replace_plugin, content)


class TFCPS_CodeUnitSpecific_Android_CLI:

    @staticmethod
    @GeneralUtilities.check_arguments
    def parse(file: str) -> TFCPS_CodeUnitSpecific_Android_Functions:
        parser = TFCPS_CodeUnitSpecific_Base_CLI.get_base_parser()
        #add custom parameter if desired
        args = parser.parse_args()
        result: TFCPS_CodeUnitSpecific_Android_Functions = TFCPS_CodeUnitSpecific_Android_Functions(file, LogLevel(int(args.verbosity)), args.targetenvironmenttype, not args.nocache, args.ispremerge)
        return result
