import os
import platform
import shutil
import re
import socket
import zipfile
from ...GeneralUtilities import GeneralUtilities
from ...SCLog import  LogLevel
from ...ScriptCollectionCore import ScriptCollectionCore
from ..TFCPS_CodeUnitSpecific_Base import TFCPS_CodeUnitSpecific_Base,TFCPS_CodeUnitSpecific_Base_CLI
from ..TFCPS_RemoteBuild import TFCPS_RemoteBuild, RunnerOperatingSystem

class TFCPS_CodeUnitSpecific_Flutter_Functions(TFCPS_CodeUnitSpecific_Base):
 
    def __init__(self,current_file:str,verbosity:LogLevel,targetenvironmenttype:str,use_cache:bool,is_pre_merge:bool):
        super().__init__(current_file, verbosity,targetenvironmenttype,use_cache,is_pre_merge)


    @GeneralUtilities.check_arguments
    def build(self,package_name:str,targets:list[str]) -> None:
        codeunit_folder = self.get_codeunit_folder()
        codeunit_name = os.path.basename(codeunit_folder)
        src_folder: str = None
        if package_name is None:
            src_folder = codeunit_folder
        else:
            src_folder = GeneralUtilities.resolve_relative_path(package_name, codeunit_folder) # TODO replace packagename
        artifacts_folder = os.path.join(codeunit_folder, "Other", "Artifacts")
        
        target_names: dict[str, str] = {
            "web": "WebApplication",
            "windows": "Windows",
            "linux": "Linux",
            "macos": "MacOS",
            "ios": "IOS",
            "android": "Android",
        }
        for target in targets:
            self._protected_sc.log.log(f"Build flutter-codeunit {codeunit_name} for target {target_names[target]}...")
            if target == "web":
                self._protected_sc.run_with_epew("flutter", "build web", src_folder)
                web_relase_folder = os.path.join(src_folder, "build/web")
                web_folder = os.path.join(artifacts_folder, "BuildResult_WebApplication")
                GeneralUtilities.ensure_directory_does_not_exist(web_folder)
                GeneralUtilities.ensure_directory_exists(web_folder)
                GeneralUtilities.copy_content_of_folder(web_relase_folder, web_folder)
            elif target == "windows":
                # Windows-builds prefer a Windows-task-runner - even when building on a Windows-client - so that all builds
                # are produced uniformly in the same defined environment. See the remote-build-article in the reference. If
                # no runner is configured, fall back to building locally (only possible when already running on Windows)
                # instead of failing, so a development machine without a configured runner is not blocked.
                if platform.system() == "Windows" and not TFCPS_RemoteBuild(self._protected_sc).has_any_runner_configured():
                    self._protected_sc.log.log("No remote-build-runner is configured; building the windows-target locally "
                                                "instead. This build is not guaranteed to be produced in the same uniform "
                                                "environment as a runner-built one.", LogLevel.Warning)
                    self._protected_sc.run_with_epew("flutter", "build windows", src_folder)
                else:
                    self.run_program_on_remote_runner(RunnerOperatingSystem.Windows, "flutter", ["build", "windows"], src_folder)
                windows_release_folder = os.path.join(src_folder, "build/windows/x64/runner/Release")
                windows_folder = os.path.join(artifacts_folder, "BuildResult_Windows")
                GeneralUtilities.ensure_directory_does_not_exist(windows_folder)
                GeneralUtilities.ensure_directory_exists(windows_folder)
                GeneralUtilities.copy_content_of_folder(windows_release_folder, windows_folder)
            elif target == "linux":
                # Linux-desktop-builds run in a sibling-container of the "SCBuilder"-image (defined in
                # ".ScriptCollection/OCIImages/ImageDefinition.csv" of the repository, like every other image the
                # build uses), which has the Linux-desktop-toolchain (clang/cmake/ninja/libgtk-3-dev) this target
                # needs. Unlike windows/ios/appbundle this is not a permanently-running remote-task-runner: SCBuilder
                # is started fresh, just for this one build-step, and removed again afterwards.
                self.__build_linux_in_container(codeunit_folder, src_folder)
                linux_release_folder = os.path.join(src_folder, "build/linux/x64/release/bundle")
                linux_folder = os.path.join(artifacts_folder, "BuildResult_Linux")
                GeneralUtilities.ensure_directory_does_not_exist(linux_folder)
                GeneralUtilities.ensure_directory_exists(linux_folder)
                GeneralUtilities.copy_content_of_folder(linux_release_folder, linux_folder)
            elif target == "macos":
                # macOS-desktop-builds must run on macOS and therefore always run on the macOS-task-runner (uniform
                # builds), analogous to how ios-builds always run on the iOS-task-runner. See SCTaskRunnerMacOS and
                # the remote-build-article in the reference.
                self.run_program_on_remote_runner(RunnerOperatingSystem.MacOS, "flutter", ["build", "macos"], src_folder)
                macos_release_folder = os.path.join(src_folder, "build/macos/Build/Products/Release")
                macos_folder = os.path.join(artifacts_folder, "BuildResult_MacOS")
                GeneralUtilities.ensure_directory_does_not_exist(macos_folder)
                GeneralUtilities.ensure_directory_exists(macos_folder)
                GeneralUtilities.copy_content_of_folder(macos_release_folder, macos_folder)
            elif target == "ios":
                # iOS-builds must run on macOS and therefore always run on the dedicated iOS-task-runner (uniform
                # builds). See SCTaskRunnerIOS and the remote-build-article in the reference.
                self.run_program_on_remote_runner(RunnerOperatingSystem.IOS, "flutter", ["build", "ios"], src_folder)
                ios_release_folder = os.path.join(src_folder, "build/ios/iphoneos")
                ios_folder = os.path.join(artifacts_folder, "BuildResult_IOS")
                GeneralUtilities.ensure_directory_does_not_exist(ios_folder)
                GeneralUtilities.ensure_directory_exists(ios_folder)
                GeneralUtilities.copy_content_of_folder(ios_release_folder, ios_folder)
            elif target == "android":
                # Android-app-builds always run on an Android-task-runner (see SCTaskRunnerAndroid and the
                # remote-build-article in the reference), analogous to how ios-builds always run on a macOS-task-runner:
                # the Android-SDK/NDK-toolchain no longer lives in SCBuilder itself, it moved into SCTaskRunnerAndroid.
                self.run_program_on_remote_runner(RunnerOperatingSystem.Android, "flutter", ["build", "appbundle"], src_folder)
                enabled=False
                if enabled:#TODO move to external because this is not platform indepent
                    aab_folder = os.path.join(artifacts_folder, "BuildResult_AAB")
                    GeneralUtilities.ensure_directory_does_not_exist(aab_folder)
                    GeneralUtilities.ensure_directory_exists(aab_folder)
                    aab_relase_folder = os.path.join(src_folder, "build/app/outputs/bundle/release")
                    aab_file_original = self._protected_sc.find_file_by_extension(aab_relase_folder, "aab")
                    aab_file = os.path.join(aab_folder, f"{codeunit_name}.aab")
                    shutil.copyfile(aab_file_original, aab_file)
                    
                    bundletool = self.tfcps_Tools_General.ensure_androidappbundletool_is_available(None,self.use_cache())
                    apk_folder = os.path.join(artifacts_folder, "BuildResult_APK")
                    GeneralUtilities.ensure_directory_does_not_exist(apk_folder)
                    GeneralUtilities.ensure_directory_exists(apk_folder)
                    apks_file = f"{apk_folder}/{codeunit_name}.apks"
                    self._protected_sc.run_program("java", f"-jar {bundletool} build-apks --bundle={aab_file} --output={apks_file} --mode=universal", aab_relase_folder)
                    with zipfile.ZipFile(apks_file, "r") as zip_ref:
                        zip_ref.extract("universal.apk", apk_folder)
                    GeneralUtilities.ensure_file_does_not_exist(apks_file)
                    os.rename(f"{apk_folder}/universal.apk", f"{apk_folder}/{codeunit_name}.apk")
            else:
                raise ValueError(f"Not supported target: {target}")
        self.copy_source_files_to_output_directory()
        if len(targets) == 0:
            # A pure Dart/Flutter library codeunit (no platform target) has no compiled artifact of its own, but
            # TFCPS_CodeUnit_BuildCodeUnit.build_codeunit() requires a 'BuildResult_.+'-matching artifact for every
            # codeunit. Publish a copy of the SourceCode-artifact under a BuildResult_-name to satisfy that generic
            # check instead of weakening it for every codeunit type. The SourceCode-artifact folder itself keeps its
            # name unchanged because the DependentCodeUnits-convention (see the reference) already relies on it.
            source_code_folder = os.path.join(artifacts_folder, "SourceCode")
            build_result_source_code_folder = os.path.join(artifacts_folder, "BuildResult_SourceCode")
            GeneralUtilities.ensure_directory_does_not_exist(build_result_source_code_folder)
            GeneralUtilities.ensure_directory_exists(build_result_source_code_folder)
            GeneralUtilities.copy_content_of_folder(source_code_folder, build_result_source_code_folder)

    @GeneralUtilities.check_arguments
    def linting(self) -> None:
        codeunit_folder = self.get_codeunit_folder()
        self._protected_sc.normalize_invisible_characters_of_files_in_folder(codeunit_folder, ["java","dart", "kt", "html"])
        #TODO call the flutter-linting here when available

    @GeneralUtilities.check_arguments
    def do_common_tasks(self,current_codeunit_version:str,package_name:str )-> None:
        self.do_common_tasks_base(current_codeunit_version)
        # The codeunit-version is the single source of truth for the version of a flutter/dart-codeunit, so the
        # version of its package (which pub itself never derives from anything else) has to be kept in sync with it.
        repository_folder = self.get_repository_folder()
        version = current_codeunit_version if current_codeunit_version is not None else self.tfcps_Tools_General.get_version_of_project(repository_folder)
        pubspec_file = os.path.join(self.get_codeunit_folder(), package_name, "pubspec.yaml")
        content = GeneralUtilities.read_text_from_file(pubspec_file)
        content = re.sub(r"(?m)^version:.*$", f"version: {version}", content, count=1)
        GeneralUtilities.write_text_to_file(pubspec_file, content)

    @GeneralUtilities.check_arguments
    def generate_reference(self) -> None:
        self.generate_reference_using_docfx()

    
    @GeneralUtilities.check_arguments
    def run_testcases(self,package_name:str) -> None:
        codeunit_folder = self.get_codeunit_folder()
        repository_folder = GeneralUtilities.resolve_relative_path("..", codeunit_folder)
        codeunit_name = os.path.basename(codeunit_folder)
        src_folder = GeneralUtilities.resolve_relative_path(package_name, codeunit_folder)
        
        self._protected_sc.run_with_epew("flutter", "test --coverage", src_folder)
        test_coverage_folder_relative = "Other/Artifacts/TestCoverage"
        test_coverage_folder = GeneralUtilities.resolve_relative_path(test_coverage_folder_relative, codeunit_folder)
        GeneralUtilities.ensure_directory_exists(test_coverage_folder)
        coverage_file_relative = f"{test_coverage_folder_relative}/TestCoverage.xml"
        coverage_file = GeneralUtilities.resolve_relative_path(coverage_file_relative, codeunit_folder)
        self._protected_sc.run_with_epew("lcov_cobertura", f"coverage/lcov.info --base-dir . --excludes test --output ../{coverage_file_relative} --demangle", src_folder)

        # format correctly
        content = GeneralUtilities.read_text_from_file(coverage_file)
        content = re.sub('<![^<]+>', '', content)
        content = re.sub('\\\\', '/', content)
        content = self.__rewrite_flutter_coverage_package_names(content, codeunit_name)
        content = re.sub('\\ filename=\\"lib/', f' filename="{package_name}/lib/', content)
        GeneralUtilities.write_text_to_file(coverage_file, content)
        self.tfcps_Tools_General.merge_packages(coverage_file, codeunit_name)
        self.tfcps_Tools_General.calculate_entire_line_rate(coverage_file)
        self.run_testcases_common_post_task(repository_folder, codeunit_name, True, self.get_target_environment_type())

    @GeneralUtilities.check_arguments
    def __build_linux_in_container(self, codeunit_folder: str, src_folder: str) -> None:
        """Runs "flutter build linux" inside a sibling-container of the "SCBuilder"-image (see the "linux"-branch of
        build() for why). If this process itself already runs inside a container (e.g. a "scbuildcodeunits -c"-run),
        the sibling-container is given access to the same volumes via "--volumes-from" instead of a bind-mount: a
        bind-mount of a path of this container would be resolved by the docker-daemon of the host, where that path
        does not exist or points to unrelated data (same reasoning as TFCPS_VisualRegressionTests)."""
        repository_folder = self.get_repository_folder()
        image = self.tfcps_Tools_General.oci_image_manager.get_registry_address_for_image_with_default_tag(repository_folder, "SCBuilder")
        image_address, image_tag = ScriptCollectionCore.split_image_address_and_tag(image)
        self._protected_sc.docker_pull(image_address, image_tag)
        working_directory_relative = os.path.relpath(src_folder, codeunit_folder).replace("\\", "/").strip("/")
        if self.__is_running_in_container():
            mount_arguments = ["--volumes-from", self.__get_own_container_id()]
            codeunit_folder_in_container = codeunit_folder.replace("\\", "/")
        else:
            codeunit_folder_in_container = "/codeunit"
            mount_arguments = ["-v", f"{codeunit_folder}:{codeunit_folder_in_container}"]
        working_folder = codeunit_folder_in_container if working_directory_relative in ("", ".") else f"{codeunit_folder_in_container}/{working_directory_relative}"
        arguments = ["run", "--rm"]+mount_arguments+["-w", working_folder, image, "flutter", "build", "linux"]
        self._protected_sc.run_program_argsasarray("docker", arguments, print_live_output=True)

    @GeneralUtilities.check_arguments
    def __is_running_in_container(self) -> bool:
        # The filesystem-marker is checked in addition to the convention-based environment-variable because a wrong
        # result here does not only change a message but makes the sibling-container access the wrong folder.
        return os.path.exists("/.dockerenv") or self._protected_sc.is_runnning_in_container()

    @GeneralUtilities.check_arguments
    def __get_own_container_id(self) -> str:
        # Determines the id of the container this process runs in, so that its volumes can be shared with the
        # SCBuilder-sibling-container via "docker run --volumes-from" (see TFCPS_VisualRegressionTests, which uses
        # the identical approach for the same reason).
        try:
            with open("/proc/self/mountinfo", "r", encoding="utf-8") as file_handle:
                match = re.search(r"/containers/([0-9a-f]{64})/", file_handle.read())
                if match is not None:
                    return match.group(1)
        except OSError:
            pass
        try:
            with open("/proc/self/cgroup", "r", encoding="utf-8") as file_handle:
                match = re.search(r"[0-9a-f]{64}", file_handle.read())
                if match is not None:
                    return match.group(0)
        except OSError:
            pass
        return socket.gethostname()

    @staticmethod
    def __rewrite_flutter_coverage_package_names(cobertura_xml_content:str,codeunit_name:str) -> str:
        """lcov_cobertura names a package after its source-subfolder relative to "lib" (for example "lib" itself
        for a file directly in "lib", "lib.chess" for a file in "lib/chess"), which has nothing to do with the
        codeunit-name. TFCPS_Tools_General.merge_packages expects every package of this coverage-file to equal the
        codeunit-name or to be dotted below it, so every "lib"-prefix is rewritten to the codeunit-name here
        instead: "lib" becomes "<codeunit-name>", "lib.chess" becomes "<codeunit-name>.chess". Without this,
        merge_packages either keeps nothing (a Flutter-codeunit's packages never actually match the codeunit-name)
        or - once the codeunit's lib-folder has only that single, unprefixed "lib"-package - crashes outright,
        because merge_packages is not the only caller which expects every package to have a name."""
        return re.sub(r' name="lib(\.[^"]*)?"', lambda match: f' name="{codeunit_name}{match.group(1) or ""}"', cobertura_xml_content)
    
    
    def get_dependencies(self)->dict[str,set[str]]:
        return dict[str,set[str]]()#TODO
    
    @GeneralUtilities.check_arguments
    def get_available_versions(self,dependencyname:str)->list[str]:
        return []#TODO
    
    def set_dependency_version(self,name:str,new_version:str)->None:
        raise ValueError(f"Operation is not implemented.")
    
class TFCPS_CodeUnitSpecific_Flutter_CLI:

    @staticmethod
    @GeneralUtilities.check_arguments
    def parse(file:str)->TFCPS_CodeUnitSpecific_Flutter_Functions:
        parser=TFCPS_CodeUnitSpecific_Base_CLI.get_base_parser()
        #add custom parameter if desired
        args=parser.parse_args()
        result:TFCPS_CodeUnitSpecific_Flutter_Functions=TFCPS_CodeUnitSpecific_Flutter_Functions(file,LogLevel(int(args.verbosity)),args.targetenvironmenttype,not args.nocache,args.ispremerge)
        return result
