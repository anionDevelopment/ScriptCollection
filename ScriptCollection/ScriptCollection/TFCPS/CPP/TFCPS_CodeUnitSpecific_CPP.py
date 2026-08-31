import os
import re
import glob
import platform
import shutil
from ...GeneralUtilities import GeneralUtilities
from ...SCLog import LogLevel
from ..TFCPS_CodeUnitSpecific_Base import TFCPS_CodeUnitSpecific_Base, TFCPS_CodeUnitSpecific_Base_CLI
from ..TFCPS_RemoteBuild import TFCPS_RemoteBuild, RunnerOperatingSystem


class TFCPS_CodeUnitSpecific_CPP_Functions(TFCPS_CodeUnitSpecific_Base):
    """Implements the tasks of a codeunit which contains a native C/C++-project.

    Unlike the other codeunit-kinds this class does not run one fixed build-tool: there is no single, universal
    C/C++-build-tool the way cargo is for Rust or flutter is for Dart, and a codeunit of this kind can even vendor
    a foreign upstream which brings its own, unrelated build-system per target-platform. Which command builds
    which target-platform is therefore configured by the codeunit itself via the public attributes below, before
    build() is called; what this class standardizes is the plumbing around that (locating the sourcecode,
    verifying the result, publishing it as an artifact, and - for the linux-target - the option to build inside a
    docker-container so that target is reproducible independent of the host-operating-system)."""

    # Architectures which are built for every target-platform, for example ["x64"] or ["x64", "arm64"].
    architectures: list[str]

    # Build-configuration which is passed to the build-tool, for example "Release" or "Debug".
    configuration: str

    # Windows: path (relative to the sourcecode-folder) of the Visual-Studio-solution which is built with MSBuild.
    # Must be set by the codeunit before build(["windows"]) is called.
    windows_solution_file: str | None

    # Windows: folder (relative to the sourcecode-folder) MSBuild writes its output into, for example
    # "bin/{architecture}/{configuration}". "{architecture}" and "{configuration}" are replaced with the values of
    # the attributes above.
    windows_output_folder_pattern: str

    # Linux/macOS: shell-commands which are run (in this order, in the sourcecode-folder) to build the project.
    linux_build_commands: list[str]
    macos_build_commands: list[str]

    # Linux/macOS: glob-patterns (relative to the sourcecode-folder) which select the files published as the
    # build-artifact.
    linux_output_file_patterns: list[str]
    macos_output_file_patterns: list[str]

    # Linux: whether the build runs inside a docker-container. Recommended (and the default): this makes the
    # linux-target reproducible on every host-operating-system instead of depending on whatever happens to be
    # installed on the machine which runs the build.
    linux_use_docker: bool

    # Linux: the name of the docker-image the build runs in (only used if linux_use_docker is True), as defined
    # in this repository's ".ScriptCollection/OCIImages/ImageDefinition.csv" (for example "Debian") - not a raw
    # image-reference. It is resolved the same way every other codeunit resolves an image it depends on (see
    # OCIImageManager.get_registry_address_for_image_with_default_tag), so a custom-registry-override defined for
    # this machine (see OCIImageManager.get_global_docker_image_registries_file) also applies here.
    linux_docker_image: str

    # Linux: shell-commands which are run once inside the container before linux_build_commands, for example to
    # install build-dependencies (for example "apt-get update", "apt-get install -y ...").
    linux_docker_setup_commands: list[str]

    def __init__(self, current_file: str, verbosity: LogLevel, targetenvironmenttype: str, use_cache: bool, is_pre_merge: bool):
        super().__init__(current_file, verbosity, targetenvironmenttype, use_cache, is_pre_merge)
        self.architectures = ["x64"]
        self.configuration = "Release"
        self.windows_solution_file = None
        self.windows_output_folder_pattern = "bin/{architecture}/{configuration}"
        self.linux_build_commands = ["./configure", "make"]
        self.macos_build_commands = ["./configure", "make"]
        self.linux_output_file_patterns = []
        self.macos_output_file_patterns = []
        self.linux_use_docker = True
        self.linux_docker_image = "Debian"
        self.linux_docker_setup_commands = []

    @GeneralUtilities.check_arguments
    def build(self, target_platforms: list[str]) -> None:
        for target_platform in target_platforms:
            if target_platform == "windows":
                self.__build_windows()
            elif target_platform == "linux":
                self.__build_linux()
            elif target_platform == "macos":
                self.__build_macos()
            else:
                raise ValueError(f"Not supported target-platform: {target_platform}")

    @GeneralUtilities.check_arguments
    def __get_source_folder(self) -> str:
        source_folder = os.path.join(self.get_codeunit_folder(), "src")
        GeneralUtilities.assert_condition(os.path.isdir(source_folder), f"The sourcecode-folder \"{source_folder}\" does not exist. Run CommonTasks.py first.")
        return source_folder

    @GeneralUtilities.check_arguments
    def __build_windows(self) -> None:
        GeneralUtilities.assert_condition(GeneralUtilities.string_has_content(self.windows_solution_file), "windows_solution_file must be set before building the windows-target of a C/C++-codeunit.")
        source_folder = self.__get_source_folder()
        solution_file = os.path.join(source_folder, self.windows_solution_file)
        GeneralUtilities.assert_condition(os.path.isfile(solution_file), f"The solution-file \"{solution_file}\" does not exist.")
        msbuild_path = self.__find_msbuild_path()
        # A vcxproj commonly pins a fixed WindowsTargetPlatformVersion, which only happens to build if that exact
        # Windows-SDK-version is installed. Passing it here as a global MSBuild-property overrides that pin (a
        # project can not override a property given on the command line) with whatever Windows-SDK is actually
        # installed on this machine, without having to patch the project.
        windows_sdk_version = self.__detect_latest_windows_sdk_version()
        for architecture in self.architectures:
            self._protected_sc.log.log(f"Build windows-target for architecture \"{architecture}\" ({self.configuration})...")
            msbuild_arguments = [solution_file, "/t:Rebuild", f"/p:Platform={architecture}", f"/p:Configuration={self.configuration}", "/m", "/nologo"]
            if windows_sdk_version is not None:
                msbuild_arguments.append(f"/p:WindowsTargetPlatformVersion={windows_sdk_version}")
            self._protected_sc.run_program_argsasarray(msbuild_path, msbuild_arguments, source_folder, print_live_output=self.get_verbosity() == LogLevel.Debug)
            output_folder = os.path.join(source_folder, self.windows_output_folder_pattern.format(architecture=architecture, configuration=self.configuration))
            GeneralUtilities.assert_condition(os.path.isdir(output_folder), f"The build did not produce the expected output-folder \"{output_folder}\".")
            target_folder = os.path.join(self.get_artifacts_folder(), f"BuildResult_Windows_{architecture}")
            GeneralUtilities.ensure_directory_does_not_exist(target_folder)
            GeneralUtilities.ensure_directory_exists(target_folder)
            GeneralUtilities.copy_content_of_folder(output_folder, target_folder)

    @GeneralUtilities.check_arguments
    def __find_msbuild_path(self) -> str:
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        vswhere_path = os.path.join(program_files_x86, "Microsoft Visual Studio", "Installer", "vswhere.exe")
        GeneralUtilities.assert_condition(os.path.isfile(vswhere_path), f"\"{vswhere_path}\" was not found. Visual Studio (with the \"Desktop development with C++\"-workload) must be installed to "
                                           "build the windows-target of a C/C++-codeunit.")
        result = self._protected_sc.run_program_argsasarray(vswhere_path, ["-latest", "-products", "*", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
                                                              GeneralUtilities.get_temp_folder())
        installation_path = result[1].strip()
        GeneralUtilities.assert_condition(GeneralUtilities.string_has_content(installation_path), "No Visual-Studio-installation with the \"Microsoft.VisualStudio.Component.VC.Tools.x86.x64\"-component was found.")
        msbuild_path = os.path.join(installation_path, "MSBuild", "Current", "Bin", "amd64", "MSBuild.exe")
        GeneralUtilities.assert_condition(os.path.isfile(msbuild_path), f"\"{msbuild_path}\" does not exist.")
        return msbuild_path

    @GeneralUtilities.check_arguments
    def __detect_latest_windows_sdk_version(self) -> str | None:
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        include_folder = os.path.join(program_files_x86, "Windows Kits", "10", "Include")
        if not os.path.isdir(include_folder):
            return None
        versions = [name for name in os.listdir(include_folder) if re.match(r"^\d+\.\d+\.\d+\.\d+$", name) and os.path.isdir(os.path.join(include_folder, name))]
        if len(versions) == 0:
            return None
        return sorted(versions, key=lambda version: [int(part) for part in version.split(".")])[-1]

    @GeneralUtilities.check_arguments
    def __build_linux(self) -> None:
        GeneralUtilities.assert_condition(0 < len(self.linux_output_file_patterns), "linux_output_file_patterns must be set before building the linux-target of a C/C++-codeunit.")
        source_folder = self.__get_source_folder()
        self._protected_sc.log.log(f"Build linux-target ({self.configuration})...")
        if self.linux_use_docker:
            self.__run_commands_in_docker(self.linux_docker_image, self.linux_docker_setup_commands, self.linux_build_commands, source_folder)
        else:
            GeneralUtilities.assert_condition(platform.system() == "Linux", "linux_use_docker is False, so the linux-target of a C/C++-codeunit can only be built locally on a Linux-host.")
            self.__run_commands_locally(self.linux_build_commands, source_folder)
        self.__collect_output_files(source_folder, self.linux_output_file_patterns, "BuildResult_Linux")

    @GeneralUtilities.check_arguments
    def __build_macos(self) -> None:
        GeneralUtilities.assert_condition(0 < len(self.macos_output_file_patterns), "macos_output_file_patterns must be set before building the macos-target of a C/C++-codeunit.")
        source_folder = self.__get_source_folder()
        self._protected_sc.log.log(f"Build macos-target ({self.configuration})...")
        if platform.system() == "Darwin":
            self.__run_commands_locally(self.macos_build_commands, source_folder)
        else:
            # macOS-binaries can only be produced on macOS, so this always delegates to a macOS-task-runner when not
            # already running on macOS (see the remote-build-article in the reference).
            self.run_program_on_remote_runner(RunnerOperatingSystem.MacOS, "/bin/sh", ["-c", " && ".join(self.macos_build_commands)], source_folder)
        self.__collect_output_files(source_folder, self.macos_output_file_patterns, "BuildResult_MacOS")

    @GeneralUtilities.check_arguments
    def __run_commands_locally(self, commands: list[str], working_directory: str) -> None:
        for command in commands:
            self._protected_sc.run_program_argsasarray("/bin/sh", ["-c", command], working_directory, print_live_output=True)

    @GeneralUtilities.check_arguments
    def __run_commands_in_docker(self, image_name: str, setup_commands: list[str], build_commands: list[str], source_folder: str) -> None:
        shell_script = " && ".join(list(setup_commands) + list(build_commands))
        GeneralUtilities.assert_condition(GeneralUtilities.string_has_content(shell_script), "linux_build_commands must not be empty.")
        # Resolved the same way every other codeunit resolves an image it depends on, so this also honors a
        # custom-registry-override defined for the machine which runs the build.
        image = self.tfcps_Tools_General.oci_image_manager.get_registry_address_for_image_with_default_tag(self.get_repository_folder(), image_name)
        # The whole codeunit-folder is mounted (not only the sourcecode-folder), so a codeunit whose build depends
        # on another one can also see what was placed at Other/Resources/DependentCodeUnits, exactly as it would
        # see it building locally.
        codeunit_folder = self.get_codeunit_folder()
        working_directory_in_container = "/workspace/" + os.path.relpath(source_folder, codeunit_folder).replace("\\", "/")
        self._protected_sc.run_program_argsasarray("docker", ["run", "--rm", "-v", f"{codeunit_folder}:/workspace", "-w", working_directory_in_container, image, "/bin/sh", "-c", shell_script],
                                                     source_folder, print_live_output=True)

    @GeneralUtilities.check_arguments
    def __collect_output_files(self, source_folder: str, patterns: list[str], artifact_name: str) -> None:
        target_folder = os.path.join(self.get_artifacts_folder(), artifact_name)
        GeneralUtilities.ensure_directory_does_not_exist(target_folder)
        GeneralUtilities.ensure_directory_exists(target_folder)
        found_any = False
        for pattern in patterns:
            for match in glob.glob(os.path.join(source_folder, pattern)):
                if os.path.isfile(match):
                    shutil.copyfile(match, os.path.join(target_folder, os.path.basename(match)))
                    found_any = True
        GeneralUtilities.assert_condition(found_any, f"The build did not produce any file matching {patterns} in \"{source_folder}\".")

    @GeneralUtilities.check_arguments
    def linting(self) -> None:
        # There is no single, universal C/C++-linter (unlike e.g. clippy for Rust), and a codeunit of this kind can
        # even vendor a foreign upstream whose sourcecode must not be changed here at all. What every codeunit of
        # this kind owns regardless of that is its own scripts, so only those are normalized by default.
        # TODO add real C/C++-linting (for example clang-format/clang-tidy) once a codeunit needs it for its own sourcecode.
        self._protected_sc.normalize_invisible_characters_of_files_in_folder(os.path.join(self.get_codeunit_folder(), "Other"), ["py", "md", "xml"])

    @GeneralUtilities.check_arguments
    def do_common_tasks(self, current_codeunit_version: str) -> None:
        self.do_common_tasks_base(current_codeunit_version)

    @GeneralUtilities.check_arguments
    def generate_reference(self) -> None:
        self.generate_reference_using_docfx()

    @GeneralUtilities.check_arguments
    def run_testcases(self) -> None:
        raise ValueError("Operation is not implemented.")  # TODO

    def get_dependencies(self) -> dict[str, set[str]]:
        return dict[str, set[str]]()  # TODO

    @GeneralUtilities.check_arguments
    def get_available_versions(self, dependencyname: str) -> list[str]:
        return []  # TODO

    def set_dependency_version(self, name: str, new_version: str) -> None:
        raise ValueError("Operation is not implemented.")


class TFCPS_CodeUnitSpecific_CPP_CLI:

    @staticmethod
    @GeneralUtilities.check_arguments
    def parse(file: str) -> TFCPS_CodeUnitSpecific_CPP_Functions:
        parser = TFCPS_CodeUnitSpecific_Base_CLI.get_base_parser()
        # add custom parameter if desired
        args = parser.parse_args()
        result: TFCPS_CodeUnitSpecific_CPP_Functions = TFCPS_CodeUnitSpecific_CPP_Functions(file, LogLevel(int(args.verbosity)), args.targetenvironmenttype, not args.nocache, args.ispremerge)
        return result
