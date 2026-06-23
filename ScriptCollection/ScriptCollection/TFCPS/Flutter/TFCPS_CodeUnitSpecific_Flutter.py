import os
import shutil
import re
import zipfile
from ...GeneralUtilities import GeneralUtilities
from ...SCLog import  LogLevel
from ..TFCPS_CodeUnitSpecific_Base import TFCPS_CodeUnitSpecific_Base,TFCPS_CodeUnitSpecific_Base_CLI
from ..TFCPS_RemoteBuild import RunnerOperatingSystem

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
            "ios": "IOS",
            "appbundle": "Android",
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
                # Windows-builds always run on a Windows-task-runner - even when building on a Windows-client - so that all
                # builds are produced uniformly in the same defined environment. See the remote-build-article in the reference.
                self.run_program_on_remote_runner(RunnerOperatingSystem.Windows, "flutter", ["build", "windows"], src_folder)
                windows_release_folder = os.path.join(src_folder, "build/windows/x64/runner/Release")
                windows_folder = os.path.join(artifacts_folder, "BuildResult_Windows")
                GeneralUtilities.ensure_directory_does_not_exist(windows_folder)
                GeneralUtilities.ensure_directory_exists(windows_folder)
                GeneralUtilities.copy_content_of_folder(windows_release_folder, windows_folder)
            elif target == "ios":
                # iOS-builds must run on macOS and therefore always run on a macOS-task-runner (uniform builds). See the
                # remote-build-article in the reference.
                self.run_program_on_remote_runner(RunnerOperatingSystem.MacOS, "flutter", ["build", "ios"], src_folder)
                ios_release_folder = os.path.join(src_folder, "build/ios/iphoneos")
                ios_folder = os.path.join(artifacts_folder, "BuildResult_IOS")
                GeneralUtilities.ensure_directory_does_not_exist(ios_folder)
                GeneralUtilities.ensure_directory_exists(ios_folder)
                GeneralUtilities.copy_content_of_folder(ios_release_folder, ios_folder)
            elif target == "appbundle":
                self._protected_sc.run_with_epew("flutter", "build appbundle", src_folder)
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

    @GeneralUtilities.check_arguments
    def linting(self) -> None:
        pass#TODO

    @GeneralUtilities.check_arguments
    def do_common_tasks(self,current_codeunit_version:str )-> None:
        self.do_common_tasks_base(current_codeunit_version)

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
        content = re.sub('\\ name=\\"lib\\"', '', content)
        content = re.sub('\\ filename=\\"lib/', f' filename="{package_name}/lib/', content)
        GeneralUtilities.write_text_to_file(coverage_file, content)
        self.tfcps_Tools_General.merge_packages(coverage_file, self.get_codeunit_name())
        self.tfcps_Tools_General.calculate_entire_line_rate(coverage_file)
        self.run_testcases_common_post_task(repository_folder, codeunit_name, True, self.get_target_environment_type())
    
    
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
