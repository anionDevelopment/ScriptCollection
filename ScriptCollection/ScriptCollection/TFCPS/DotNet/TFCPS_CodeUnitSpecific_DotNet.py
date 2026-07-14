import os
import re
import shutil
import uuid
import json
import csv
from lxml import etree
import yaml
from .CertificateGeneratorInformationBase import CertificateGeneratorInformationBase
from ...GeneralUtilities import GeneralUtilities
from ...SCLog import  LogLevel
from ..TFCPS_CodeUnitSpecific_Base import TFCPS_CodeUnitSpecific_Base,TFCPS_CodeUnitSpecific_Base_CLI

class TFCPS_CodeUnitSpecific_DotNet_Functions(TFCPS_CodeUnitSpecific_Base):
 
    is_library:bool = None
    csproj_file:bool = None

    def __init__(self,current_file:str,verbosity:LogLevel,targetenvironmenttype:str,use_cache:bool,is_pre_merge:bool):
        super().__init__(current_file, verbosity,targetenvironmenttype,use_cache,is_pre_merge)
        self.csproj_file=os.path.join(self.get_codeunit_folder(), self.get_codeunit_name(), self.get_codeunit_name() + ".csproj")
        self.is_library="<OutputType>Library</OutputType>" in GeneralUtilities.read_text_from_file(self.csproj_file)#TODO do a real check by checking this property using xpath

    @GeneralUtilities.check_arguments
    def build(self,runtimes:list[str],generate_open_api_spec:bool) -> None:
        self.__reset_nuget_sources()
        if self.is_library:
            self.standardized_tasks_build_for_dotnet_library_project(runtimes)
            GeneralUtilities.assert_condition(not generate_open_api_spec,"OpenAPI-Specification can not be generated for a library.")
        else:
            self.standardized_tasks_build_for_dotnet_project(runtimes)
            if generate_open_api_spec:
                self.generate_openapi_file(runtimes[0])

    @GeneralUtilities.check_arguments
    def __reset_nuget_sources(self) -> None:
        if self._protected_sc.is_running_in_build_container():
            
            self._protected_sc.log.log("Remove all existing NuGet-sources...", LogLevel.Debug)
            list_result = self._protected_sc.run_program_argsasarray("dotnet", ["nuget", "list", "source"], throw_exception_if_exitcode_is_not_zero=False,print_live_output=False)
            existing_source_name_pattern = re.compile(r"^\s*\d+\.\s+(.+?)\s+\[(?:Enabled|Disabled)\]\s*$")
            for line in list_result[1].splitlines():
                m = existing_source_name_pattern.match(line)
                if not m:
                    continue
                existing_source_name = m.group(1).strip()
                self._protected_sc.log.log(f"Remove existing NuGet-source '{existing_source_name}'", LogLevel.Debug)
                self._protected_sc.run_program_argsasarray("dotnet", ["nuget", "remove", "source", existing_source_name], throw_exception_if_exitcode_is_not_zero=False)

            sources:list[tuple[str,str,str,str]] = []
            
            csv_file = os.path.join(self._protected_sc.get_scriptcollection_configuration_folder(), "TFCPS", "CustomC#Dependencies.csv")
            if  os.path.isfile(csv_file):
                self._protected_sc.log.log(f"Add custom NuGet-sources from '{csv_file}'...",LogLevel.Debug)
                with open(csv_file, encoding="utf-8-sig", newline="") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        name = (row.get("Name") or "").strip()
                        url = (row.get("Url") or "").strip()
                        username = (row.get("Username") or "").strip()
                        password = (row.get("Password") or "").strip()
                        if not name or not url:
                            continue
                        sources.append((name, url, username, password))

            if len(os.environ.items()) > 0:
                self._protected_sc.log.log(f"Add custom NuGet-sources from environment variables...",LogLevel.Debug)
            env_name_pattern = re.compile(r"^Dependency_CSharp_(.+?)_Name$")
            for env_var_name, env_var_value in os.environ.items():
                m = env_name_pattern.match(env_var_name)
                if not m:
                    continue
                dependency_name = m.group(1)
                name = (env_var_value or "").strip()
                url = (os.environ.get(f"Dependency_CSharp_{dependency_name}_URL") or "").strip()
                username = (os.environ.get(f"Dependency_CSharp_{dependency_name}_Username") or "").strip()
                password = (os.environ.get(f"Dependency_CSharp_{dependency_name}_Passwort") or "").strip()
                if not name or not url:
                    continue
                sources.append((name, url, username, password))

            self._protected_sc.run_program_argsasarray("dotnet", ["nuget", "add", "source", "https://api.nuget.org/v3/index.json", "--name", "nuget.org"], print_live_output=True)
            for name, url, username, password in sources:
                #TODO add only the sources which are needed by the project
                self._protected_sc.log.log(f"Add NuGet-source '{name}' with url '{url}'",LogLevel.Debug)
                args = ["nuget", "add", "source", url, "--name", name]
                if username:
                    args += ["--username", username]
                if password:
                    args += ["--password", password, "--store-password-in-clear-text"]
                args_for_log = list(args)
                if password:
                    args_for_log[args_for_log.index(password)] = "***"
                self._protected_sc.run_program_argsasarray("dotnet", args, arguments_for_log=args_for_log, throw_exception_if_exitcode_is_not_zero=False, print_live_output=self.get_verbosity()==LogLevel.Debug)


            if self._protected_sc.log.loglevel==LogLevel.Debug:
                self._protected_sc.run_program_argsasarray("dotnet", ["nuget","list","source","--format","detailed"], print_live_output=True)
            else:
                self._protected_sc.run_program_argsasarray("dotnet", ["nuget","list","source"], print_live_output=True)

    @GeneralUtilities.check_arguments
    def generate_openapi_file(self, runtime: str) -> None:
        swagger_document_name: str = "APISpecification"
        self._protected_sc.log.log("Generate OpenAPI-specification-file...")
        codeunitname = self.get_codeunit_name()
        repository_folder = self.get_repository_folder()
        codeunit_folder = os.path.join(repository_folder, codeunitname)
        artifacts_folder = os.path.join(codeunit_folder, "Other", "Artifacts")
        GeneralUtilities.ensure_directory_exists(os.path.join(artifacts_folder, "APISpecification"))
        codeunit_version = self.tfcps_Tools_General.get_version_of_codeunit(os.path.join(codeunit_folder,f"{codeunitname}.codeunit.xml"))

        versioned_api_spec_file = f"APISpecification/{codeunitname}.v{codeunit_version}.api.json"
        self._protected_sc.run_program("swagger", f"tofile --output {versioned_api_spec_file} BuildResult_DotNet_{runtime}/{codeunitname}.dll {swagger_document_name}", artifacts_folder,print_live_output=self.get_verbosity()==LogLevel.Debug)
        api_file: str = os.path.join(artifacts_folder, versioned_api_spec_file)

        with open(api_file, encoding="utf-8") as api_file_content:
            reloaded_json = json.load(api_file_content)
        reloaded_json = self.__remove_carriage_returns_recursively(reloaded_json)
        json_content: str = json.dumps(reloaded_json, indent=2, ensure_ascii=False).replace("\r\n", "\n").replace("\r", "\n")
        GeneralUtilities.write_text_to_file(api_file, json_content)

        shutil.copyfile(api_file, os.path.join(artifacts_folder, f"APISpecification/{codeunitname}.latest.api.json"))

        resources_folder = os.path.join(codeunit_folder, "Other", "Resources")
        GeneralUtilities.ensure_directory_exists(resources_folder)
        resources_apispec_folder = os.path.join(resources_folder, "APISpecification")
        GeneralUtilities.ensure_directory_exists(resources_apispec_folder)
        resource_target_file = os.path.join(resources_apispec_folder, f"{codeunitname}.api.json")
        GeneralUtilities.ensure_file_does_not_exist(resource_target_file)
        shutil.copyfile(api_file, resource_target_file)

        yamlfile1: str = str(os.path.join(artifacts_folder, f"APISpecification/{codeunitname}.v{codeunit_version}.api.yaml"))
        GeneralUtilities.ensure_file_does_not_exist(yamlfile1)
        
        yaml_content: str = yaml.dump(reloaded_json, allow_unicode=True).replace("\r\n", "\n").replace("\r", "\n")
        GeneralUtilities.write_text_to_file(yamlfile1, yaml_content)

        yamlfile2: str = str(os.path.join(artifacts_folder, f"APISpecification/{codeunitname}.latest.api.yaml"))
        GeneralUtilities.ensure_file_does_not_exist(yamlfile2)
        shutil.copyfile(yamlfile1, yamlfile2)

        yamlfile3: str = str(os.path.join(resources_apispec_folder, f"{codeunitname}.api.yaml"))
        GeneralUtilities.ensure_file_does_not_exist(yamlfile3)
        shutil.copyfile(yamlfile1, yamlfile3)

    def __remove_carriage_returns_recursively(self, value):
        if isinstance(value, str):
            return value.replace("\r\n", "\n").replace("\r", "\n")
        if isinstance(value, dict):
            return {self.__remove_carriage_returns_recursively(key): self.__remove_carriage_returns_recursively(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.__remove_carriage_returns_recursively(item) for item in value]
        return value

    @GeneralUtilities.check_arguments
    def __standardized_tasks_build_for_dotnet_build(self, csproj_file: str, originaloutputfolder: str, files_to_sign: dict[str, str], commitid: str, runtimes: list[str],  target_environmenttype_mapping:  dict[str, str], copy_license_file_to_target_folder: bool, repository_folder: str, codeunit_name: str) -> None:
        self._protected_sc.assert_is_git_repository(repository_folder)
        csproj_filename = os.path.basename(csproj_file)
        self._protected_sc.log.log(f"Build {csproj_filename}...")
        dotnet_build_configuration: str = self.get_target_environment_type()
        codeunit_folder = os.path.join(repository_folder, codeunit_name)
        csproj_file_folder = os.path.dirname(csproj_file)
        csproj_file_name = os.path.basename(csproj_file)
        csproj_file_name_without_extension = csproj_file_name.split(".")[0]
        sarif_folder = os.path.join(codeunit_folder, "Other", "Resources", "CodeAnalysisResult")
        GeneralUtilities.ensure_directory_exists(sarif_folder)
        gitkeep_file = os.path.join(sarif_folder, ".gitkeep")
        GeneralUtilities.ensure_file_exists(gitkeep_file)
        for runtime in runtimes:
            outputfolder = originaloutputfolder+runtime
            GeneralUtilities.ensure_directory_does_not_exist(os.path.join(csproj_file_folder, "obj"))
            GeneralUtilities.ensure_directory_does_not_exist(outputfolder)
            self._protected_sc.run_program("dotnet", "clean", csproj_file_folder)
            GeneralUtilities.ensure_directory_exists(outputfolder)
            self._protected_sc.run_program_argsasarray("dotnet", ["restore", "--runtime", runtime], codeunit_folder,print_live_output=self.get_verbosity()==LogLevel.Debug)
            self._protected_sc.run_program_argsasarray("dotnet", ["build", "--no-restore", csproj_file_name, "-c", dotnet_build_configuration, "-o", outputfolder, "--runtime", runtime], csproj_file_folder,print_live_output=self.get_verbosity()==LogLevel.Debug)
            if copy_license_file_to_target_folder:
                license_file = os.path.join(repository_folder, "License.txt")
                target = os.path.join(outputfolder, f"{codeunit_name}.License.txt")
                shutil.copyfile(license_file, target)
            if 0 < len(files_to_sign):
                for key, value in files_to_sign.items():
                    dll_file = key
                    snk_file = value
                    dll_file_full = os.path.join(outputfolder, dll_file)
                    if os.path.isfile(dll_file_full):
                        GeneralUtilities.assert_condition(self._protected_sc.run_program("sn", f"-vf {dll_file}", outputfolder, throw_exception_if_exitcode_is_not_zero=False)[0] == 1, f"Pre-verifying of {dll_file} failed.")
                        self._protected_sc.run_program_argsasarray("sn", ["-R", dll_file, snk_file], outputfolder)
                        GeneralUtilities.assert_condition(self._protected_sc.run_program("sn", f"-vf {dll_file}", outputfolder, throw_exception_if_exitcode_is_not_zero=False)[0] == 0, f"Verifying of {dll_file} failed.")
            sarif_filename = f"{csproj_file_name_without_extension}.sarif"
            sarif_source_file = os.path.join(sarif_folder, sarif_filename)
            if os.path.exists(sarif_source_file):
                sarif_folder_target = os.path.join(codeunit_folder, "Other", "Artifacts", "CodeAnalysisResult")
                GeneralUtilities.ensure_directory_exists(sarif_folder_target)
                sarif_target_file = os.path.join(sarif_folder_target, sarif_filename)
                GeneralUtilities.ensure_file_does_not_exist(sarif_target_file)
                shutil.copyfile(sarif_source_file, sarif_target_file)

    @GeneralUtilities.check_arguments
    def standardized_tasks_build_for_dotnet_project(self,runtimes:list[str]) -> None:
        self.__standardized_tasks_build_for_dotnet_project(runtimes)

    @GeneralUtilities.check_arguments
    def standardized_tasks_build_for_dotnet_library_project(self,runtimes:list[str]) -> None:
        self.__standardized_tasks_build_for_dotnet_project(runtimes)
        self.__standardized_tasks_build_nupkg_for_dotnet_create_package(runtimes)

 
    @staticmethod
    @GeneralUtilities.check_arguments
    def get_filestosign_from_commandline_arguments( default_value: dict[str, str]) -> dict[str, str]:
        result_plain =None# TODO TasksForCommonProjectStructure.get_property_from_commandline_arguments(commandline_arguments, "sign")
        if result_plain is None:
            return default_value
        else:
            result: dict[str, str] = dict[str, str]()
            files_tuples = GeneralUtilities.to_list(result_plain, ";")
            for files_tuple in files_tuples:
                splitted = files_tuple.split("=")
                result[splitted[0]] = splitted[1]
            return result

    @GeneralUtilities.check_arguments
    def __standardized_tasks_build_for_dotnet_project(self,runtimes:list[str]) -> None:

        target_environment_type: str=self.get_target_environment_type()
        copy_license_file_to_target_folder: bool=True
        codeunitname: str = self.get_codeunit_name()
        
        workspace_folder=os.path.join(self.get_codeunit_folder(),"Other","Workspace")
        GeneralUtilities.ensure_directory_does_not_exist(workspace_folder)
        
        files_to_sign: dict[str, str] = self.get_filestosign_from_commandline_arguments(  dict())
        repository_folder: str = self.get_repository_folder()
        commitid = self._protected_sc.git_get_commit_id(repository_folder)
        outputfolder = GeneralUtilities.resolve_relative_path("./Other/Artifacts", self.get_codeunit_folder())
        codeunit_folder = os.path.join(repository_folder, codeunitname)
        csproj_file = os.path.join(codeunit_folder, codeunitname, codeunitname + ".csproj")
        csproj_test_file = os.path.join(codeunit_folder, codeunitname+"Tests", codeunitname+"Tests.csproj")
        self.__standardized_tasks_build_for_dotnet_build(csproj_file,  os.path.join(outputfolder, "BuildResult_DotNet_"), files_to_sign, commitid, runtimes, target_environment_type,  copy_license_file_to_target_folder, repository_folder, codeunitname)
        self.__standardized_tasks_build_for_dotnet_build(csproj_test_file,  os.path.join(outputfolder, "BuildResultTests_DotNet_"), files_to_sign, commitid, runtimes, target_environment_type,  copy_license_file_to_target_folder, repository_folder, codeunitname)
        self.generate_sbom_for_dotnet_project(codeunit_folder)
        self.copy_source_files_to_output_directory()

    @GeneralUtilities.check_arguments
    def __standardized_tasks_build_nupkg_for_dotnet_create_package(self,runtimes:list[str]) -> None:
        codeunitname: str = self.get_codeunit_name()        
        repository_folder: str =self.get_repository_folder()
        build_folder = os.path.join(repository_folder, codeunitname, "Other", "Build")
        outputfolder = GeneralUtilities.resolve_relative_path("./Other/Artifacts/BuildResult_NuGet",self.get_codeunit_folder())
        root: etree._ElementTree = etree.parse(os.path.join(build_folder, f"{codeunitname}.nuspec"))
        current_version = root.xpath("//*[name() = 'package']/*[name() = 'metadata']/*[name() = 'version']/text()")[0]
        nupkg_filename = f"{codeunitname}.{current_version}.nupkg"
        nupkg_file = f"{build_folder}/{nupkg_filename}"
        GeneralUtilities.ensure_file_does_not_exist(nupkg_file)
        commit_id = self._protected_sc.git_get_commit_id(repository_folder)
        nuspec_file = os.path.join(build_folder, f"{codeunitname}.nuspec")
        # Pack the hand-written nuspec using "dotnet pack" (the classic "nuget pack" is not available in the dotnet-only build-container).
        # With NuspecFile the package-content is taken entirely from the nuspec's <files>-list, so no rebuild happens here (the library was already built before).
        self._protected_sc.run_program_argsasarray("dotnet", [
            "pack", self.csproj_file,
            "-c", self.get_target_environment_type(),
            "--no-build", "--no-restore",
            "--output", build_folder,
            f"-p:NuspecFile={nuspec_file}",
            f"-p:NuspecBasePath={build_folder}",
            f"-p:NuspecProperties=commitid={commit_id}",
            "-p:IsPackable=true",
        ], build_folder, print_live_output=self.get_verbosity()==LogLevel.Debug)
        GeneralUtilities.ensure_directory_does_not_exist(outputfolder)
        GeneralUtilities.ensure_directory_exists(outputfolder)
        os.rename(nupkg_file, f"{outputfolder}/{nupkg_filename}")

    @GeneralUtilities.check_arguments
    def generate_sbom_for_dotnet_project(self, codeunit_folder: str) -> None:
        self._protected_sc.log.log("Generate SBOM...")
        codeunit_name = os.path.basename(codeunit_folder)
        bomfile_folder = "Other/Artifacts/BOM"
        self._protected_sc.run_program_argsasarray("dotnet", ["CycloneDX", f"{codeunit_name}/{codeunit_name}.csproj", "-o", bomfile_folder], codeunit_folder)
        codeunitversion = self.tfcps_Tools_General.get_version_of_codeunit(os.path.join(codeunit_folder, f"{codeunit_name}.codeunit.xml"))
        target = f"{codeunit_folder}/{bomfile_folder}/{codeunit_name}.{codeunitversion}.sbom.xml"
        GeneralUtilities.ensure_file_does_not_exist(target)
        os.rename(f"{codeunit_folder}/{bomfile_folder}/bom.xml", target)
        self._protected_sc.format_xml_file(target) 

    @GeneralUtilities.check_arguments
    def get_dotnet_build_diagnostics(self) -> list[tuple[LogLevel, str, str | None, int | None]]:
        codeunit_name = self.get_codeunit_name()
        codeunit_folder = self.get_codeunit_folder()
        sln_file = os.path.join(codeunit_folder, codeunit_name + ".sln")
        temp_output_folder = os.path.join(GeneralUtilities.get_temp_folder(), str(uuid.uuid4()))
        GeneralUtilities.ensure_directory_exists(temp_output_folder)
        # Run the build from an absolute temporary working-directory (instead of the codeunit-folder) and with node-reuse
        # disabled. Building a solution with "-o" (which is required here to keep the diagnostics-build isolated from the
        # real build-output) is not officially supported by the .NET-SDK (warning NETSDK1194) and makes MSBuild create an
        # additional "tmp/<guid>"-output-folder relative to the build-process' working-directory. With node-reuse enabled
        # that folder is even created by a reused MSBuild-worker-node that still has a codeunit-subfolder as its working-
        # directory, so it ends up inside the codeunit-folder. Such a folder is usually cleaned up by the SDK, but on a
        # bind-mounted filesystem (for example when the build runs in a Linux-container with the repository mounted from a
        # Windows-host) the cleanup can fail and the folder is left behind. By using an absolute working-directory and
        # forcing fresh worker-nodes (which inherit that working-directory) any such relative "tmp/<guid>"-folder is created
        # below temp_output_folder and removed together with it in the finally-block.
        try:
            run_result = self._protected_sc.run_program("dotnet", f"build \"{sln_file}\" -nologo -v minimal -o \"{temp_output_folder}\"", temp_output_folder, throw_exception_if_exitcode_is_not_zero=False, env_vars={"DOTNET_CLI_UI_LANGUAGE": "en-US", "MSBUILDDISABLENODEREUSE": "1"})
        finally:
            GeneralUtilities.ensure_directory_does_not_exist(temp_output_folder)
        diagnostics: list[tuple[LogLevel, str, str | None, int | None]] = []
        pattern = re.compile(r"^\s*(?:(.+?)\((\d+),\d+\): )?(error|warning|message|info) [^:]+: (.+?)(?:\s*\[.+\])?\s*$", re.IGNORECASE)
        for line in GeneralUtilities.string_to_lines(run_result[1] + "\n" + run_result[2]):
            m = pattern.match(line)
            if m:
                file_path = m.group(1)
                line_number = int(m.group(2)) if m.group(2) else None
                level_str = m.group(3).lower()
                message = m.group(4)
                if level_str == "error":
                    level = LogLevel.Error
                elif level_str == "warning":
                    level = LogLevel.Warning
                else:
                    level = LogLevel.Information
                diagnostics.append((level, message, file_path, line_number))
        return diagnostics

    @GeneralUtilities.check_arguments
    def linting(self) -> None:
        codeunit_name = self.get_codeunit_name()
        codeunit_folder = self.get_codeunit_folder()
        # Normalize the line-endings of all non-git-ignored *.cs-files in the codeunit- and the test-project to LF.
        for cs_source_folder in [os.path.join(codeunit_folder, codeunit_name), os.path.join(codeunit_folder, codeunit_name + "Tests")]:
            for cs_file in self._protected_sc.get_not_git_ignored_files_of_folder(cs_source_folder, ".cs"):
                self._protected_sc.normalize_line_endings(cs_file)
        self._protected_sc.format_xml_file(os.path.join(codeunit_folder, codeunit_name, codeunit_name + ".csproj"), add_xml_declaration=False)
        self._protected_sc.format_xml_file(os.path.join(codeunit_folder, codeunit_name + "Tests", codeunit_name + "Tests.csproj"), add_xml_declaration=False)
        self.standardized_task_verify_standard_format_csproj_files()
        diagnostics = self.get_dotnet_build_diagnostics()
        has_errors = False
        for (level, message, file, line) in diagnostics:
            location = f" ({file}:{line})" if file else ""
            self._protected_sc.log.log(f"{message}{location}", level)
            if level == LogLevel.Error:#should not occurr on scbuildcodeunits because then the build would have failed already but you can also run this script manually.
                has_errors = True
        if has_errors:
            raise ValueError("Linting-issues occurred.")

    @GeneralUtilities.check_arguments
    def do_common_tasks(self,current_codeunit_version:str,certificateGeneratorInformation:CertificateGeneratorInformationBase)-> None:
        self.do_common_tasks_base(current_codeunit_version)
        codeunit_name =self.get_codeunit_name()
        codeunit_version = self.tfcps_Tools_General.get_version_of_project(self.get_repository_folder())  # Should always be the same as the project-version #TODO make this configurable from outside
        folder_of_current_file =os.path.join(self.get_codeunit_folder(),"Other")
        self._protected_sc.replace_version_in_csproj_file(GeneralUtilities.resolve_relative_path(f"../{codeunit_name}/{codeunit_name}.csproj", folder_of_current_file), codeunit_version)
        self._protected_sc.replace_version_in_csproj_file(GeneralUtilities.resolve_relative_path(f"../{codeunit_name}Tests/{codeunit_name}Tests.csproj", folder_of_current_file), codeunit_version)
        if self.is_library:
            self._protected_sc.replace_version_in_nuspec_file(GeneralUtilities.resolve_relative_path(f"./Build/{codeunit_name}.nuspec", folder_of_current_file), codeunit_version)
        if certificateGeneratorInformation.generate_certificate():
            self.tfcps_Tools_General.set_constants_for_certificate_private_information(self.get_codeunit_folder())

    @GeneralUtilities.check_arguments
    def standardized_task_verify_standard_format_csproj_files(self) -> bool:
        codeunit_folder=self.get_codeunit_folder()
        repository_folder = os.path.dirname(codeunit_folder)
        codeunit_name = os.path.basename(codeunit_folder)
        codeunit_folder = os.path.join(repository_folder, codeunit_name)
        codeunit_version = self.tfcps_Tools_General.get_version_of_codeunit(self.get_codeunit_file())

        csproj_project_name = codeunit_name
        csproj_file = os.path.join(codeunit_folder, csproj_project_name, csproj_project_name+".csproj")
        result1: tuple[bool, str, list[str]] = self.__standardized_task_verify_standard_format_for_project_csproj_file(csproj_file, codeunit_folder, codeunit_name, codeunit_version)
        if not result1[0]:
            hints: str = "\n".join(result1[2])
            raise ValueError(f"'{csproj_file}' with content '{GeneralUtilities.read_text_from_file(csproj_file)}' does not match the standardized .csproj-file-format which is defined by the regex '{result1[1]}'.\n{hints}")
        self.__check_csproj_urls(csproj_file)

        test_csproj_project_name = csproj_project_name+"Tests"
        test_csproj_file = os.path.join(codeunit_folder, test_csproj_project_name, test_csproj_project_name+".csproj")
        result2: tuple[bool, str, list[str]] = self.__standardized_task_verify_standard_format_for_test_csproj_file(test_csproj_file, codeunit_name, codeunit_version)
        if not result2[0]:
            hints: str = "\n".join(result2[2])
            raise ValueError(f"'{test_csproj_file}' with content '{GeneralUtilities.read_text_from_file(test_csproj_file)}' does not match the standardized .csproj-file-format which is defined by the regex '{result2[1]}'.\n{hints}")
        self.__check_csproj_urls(test_csproj_file)

    @GeneralUtilities.check_arguments
    def __check_csproj_urls(self, csproj_file: str) -> None:
        remote_address: str = self.get_remote_address()
        root: etree._ElementTree = etree.parse(csproj_file)
        package_project_url: str = self.__get_unique_csproj_property_value(root, csproj_file, "PackageProjectUrl")
        repository_url: str = self.__get_unique_csproj_property_value(root, csproj_file, "RepositoryUrl")
        if package_project_url != remote_address:
            raise ValueError(f"The PackageProjectUrl-value '{package_project_url}' in '{csproj_file}' is not equal to the remote-address '{remote_address}' which is defined in the ProductInformation.xml-file of the repository.")
        expected_repository_url: str = package_project_url+".git"
        if repository_url != expected_repository_url:
            raise ValueError(f"The RepositoryUrl-value '{repository_url}' in '{csproj_file}' is not equal to the expected value '{expected_repository_url}'.")

    @GeneralUtilities.check_arguments
    def __get_unique_csproj_property_value(self, root: etree._ElementTree, csproj_file: str, property_name: str) -> str:
        values: list[str] = [str(value).strip() for value in root.xpath(f"/Project/PropertyGroup/{property_name}/text()")]
        if len(values) != 1:
            raise ValueError(f"'{csproj_file}' must contain exactly one {property_name}-element but contains {len(values)} of them.")
        return values[0]

    def __standardized_task_verify_standard_format_for_project_csproj_file(self, csproj_file: str, codeunit_folder: str, codeunit_name: str, codeunit_version: str) -> tuple[bool, str, str]:
        codeunit_name_regex = re.escape(codeunit_name)
        codeunit_description = self.tfcps_Tools_General.get_codeunit_description(self.get_codeunit_file())
        codeunit_version_regex = re.escape(codeunit_version)
        codeunit_description_regex = re.escape(codeunit_description)
        regex = f"""^<Project Sdk=\\"Microsoft\\.NET\\.Sdk\\">
  <PropertyGroup>
    <TargetFramework>([^<]+)<\\/TargetFramework>
    <Authors>([^<]+)<\\/Authors>
    <Version>{codeunit_version_regex}<\\/Version>
    <AssemblyVersion>{codeunit_version_regex}<\\/AssemblyVersion>
    <FileVersion>{codeunit_version_regex}<\\/FileVersion>
    <SelfContained>false<\\/SelfContained>
    <IsPackable>false<\\/IsPackable>
    <PreserveCompilationContext>false<\\/PreserveCompilationContext>
    <GenerateRuntimeConfigurationFiles>true<\\/GenerateRuntimeConfigurationFiles>
    <Copyright>([^<]+)<\\/Copyright>
    <Description>{codeunit_description_regex}<\\/Description>
    <PackageProjectUrl>https:\\/\\/([^<]+)<\\/PackageProjectUrl>
    <RepositoryUrl>https:\\/\\/([^<]+)\\.git<\\/RepositoryUrl>
    <RootNamespace>([^<]+)\\.Core<\\/RootNamespace>
    <ProduceReferenceAssembly>false<\\/ProduceReferenceAssembly>
    <Nullable>(disable|enable|warnings|annotations)<\\/Nullable>
    <Configurations>Development;QualityCheck;Productive<\\/Configurations>
    <IsTestProject>false<\\/IsTestProject>
    <LangVersion>([^<]+)<\\/LangVersion>
    <PackageRequireLicenseAcceptance>true<\\/PackageRequireLicenseAcceptance>
    <GenerateSerializationAssemblies>Off<\\/GenerateSerializationAssemblies>
    <AppendTargetFrameworkToOutputPath>false<\\/AppendTargetFrameworkToOutputPath>
    <OutputPath>\\.\\.\\\\Other\\\\Artifacts\\\\BuildResult_DotNet_win\\-x64<\\/OutputPath>
    <PlatformTarget>([^<]+)<\\/PlatformTarget>
    <WarningLevel>\\d<\\/WarningLevel>
    <Prefer32Bit>false<\\/Prefer32Bit>
    <SignAssembly>true<\\/SignAssembly>
    <AssemblyOriginatorKeyFile>\\.\\.\\\\\\.\\.\\\\Other\\\\Resources\\\\PublicKeys\\\\StronglyNamedKey\\\\([^<]+)PublicKey\\.snk<\\/AssemblyOriginatorKeyFile>
    <DelaySign>true<\\/DelaySign>
    <NoWarn>([^<]+)<\\/NoWarn>
    <WarningsAsErrors>([^<]+)<\\/WarningsAsErrors>
    <ErrorLog>\\.\\.\\\\Other\\\\Resources\\\\CodeAnalysisResult\\\\{codeunit_name_regex}\\.sarif<\\/ErrorLog>
    <OutputType>([^<]+)<\\/OutputType>
    <DocumentationFile>\\.\\.\\\\Other\\\\Artifacts\\\\MetaInformation\\\\{codeunit_name_regex}\\.xml<\\/DocumentationFile>(\\n|.)*
  <\\/PropertyGroup>
  <PropertyGroup Condition=\\\"'\\$\\(Configuration\\)'=='Development'\\\">
    <DebugType>full<\\/DebugType>
    <DebugSymbols>true<\\/DebugSymbols>
    <Optimize>false<\\/Optimize>
    <DefineConstants>TRACE;DEBUG;Development<\\/DefineConstants>
    <ErrorReport>prompt<\\/ErrorReport>
  <\\/PropertyGroup>
  <PropertyGroup Condition=\\\"'\\$\\(Configuration\\)'=='QualityCheck'\\\">
    <DebugType>portable<\\/DebugType>
    <DebugSymbols>true<\\/DebugSymbols>
    <Optimize>false<\\/Optimize>
    <DefineConstants>TRACE;QualityCheck<\\/DefineConstants>
    <ErrorReport>none<\\/ErrorReport>
  <\\/PropertyGroup>
  <PropertyGroup Condition=\\\"'\\$\\(Configuration\\)'=='Productive'\\\">
    <DebugType>portable<\\/DebugType>
    <DebugSymbols>true<\\/DebugSymbols>
    <Optimize>false<\\/Optimize>
    <DefineConstants>Productive<\\/DefineConstants>
    <ErrorReport>none<\\/ErrorReport>
  <\\/PropertyGroup>(\\n|.)*
<\\/Project>\\n?$"""
        result = self.__standardized_task_verify_standard_format_for_csproj_files(regex, csproj_file)
        return (result[0], regex, result[1])

    def __standardized_task_verify_standard_format_for_test_csproj_file(self, csproj_file: str, codeunit_name: str, codeunit_version: str) -> tuple[bool, str, str]:
        codeunit_name_regex = re.escape(codeunit_name)
        codeunit_version_regex = re.escape(codeunit_version)
        regex = f"""^<Project Sdk=\\"Microsoft\\.NET\\.Sdk\\">
  <PropertyGroup>
    <TargetFramework>([^<]+)<\\/TargetFramework>
    <Authors>([^<]+)<\\/Authors>
    <Version>{codeunit_version_regex}<\\/Version>
    <AssemblyVersion>{codeunit_version_regex}<\\/AssemblyVersion>
    <FileVersion>{codeunit_version_regex}<\\/FileVersion>
    <SelfContained>false<\\/SelfContained>
    <IsPackable>false<\\/IsPackable>
    <PreserveCompilationContext>false<\\/PreserveCompilationContext>
    <GenerateRuntimeConfigurationFiles>true<\\/GenerateRuntimeConfigurationFiles>
    <Copyright>([^<]+)<\\/Copyright>
    <Description>{codeunit_name_regex}Tests is the test-project for {codeunit_name_regex}\\.<\\/Description>
    <PackageProjectUrl>https:\\/\\/([^<]+)<\\/PackageProjectUrl>
    <RepositoryUrl>https:\\/\\/([^<]+)\\.git</RepositoryUrl>
    <RootNamespace>([^<]+)\\.Tests<\\/RootNamespace>
    <ProduceReferenceAssembly>false<\\/ProduceReferenceAssembly>
    <Nullable>(disable|enable|warnings|annotations)<\\/Nullable>
    <Configurations>Development;QualityCheck;Productive<\\/Configurations>
    <IsTestProject>true<\\/IsTestProject>
    <LangVersion>([^<]+)<\\/LangVersion>
    <PackageRequireLicenseAcceptance>true<\\/PackageRequireLicenseAcceptance>
    <GenerateSerializationAssemblies>Off<\\/GenerateSerializationAssemblies>
    <AppendTargetFrameworkToOutputPath>false<\\/AppendTargetFrameworkToOutputPath>
    <OutputPath>\\.\\.\\\\Other\\\\Artifacts\\\\BuildResultTests_DotNet_win\\-x64<\\/OutputPath>
    <PlatformTarget>([^<]+)<\\/PlatformTarget>
    <WarningLevel>\\d<\\/WarningLevel>
    <Prefer32Bit>false<\\/Prefer32Bit>
    <SignAssembly>true<\\/SignAssembly>
    <AssemblyOriginatorKeyFile>\\.\\.\\\\\\.\\.\\\\Other\\\\Resources\\\\PublicKeys\\\\StronglyNamedKey\\\\([^<]+)PublicKey\\.snk<\\/AssemblyOriginatorKeyFile>
    <DelaySign>true<\\/DelaySign>
    <NoWarn>([^<]+)<\\/NoWarn>
    <WarningsAsErrors>([^<]+)<\\/WarningsAsErrors>
    <ErrorLog>\\.\\.\\\\Other\\\\Resources\\\\CodeAnalysisResult\\\\{codeunit_name_regex}Tests\\.sarif<\\/ErrorLog>
    <OutputType>Library<\\/OutputType>(\\n|.)*
  <\\/PropertyGroup>
  <PropertyGroup Condition=\\\"'\\$\\(Configuration\\)'=='Development'\\\">
    <DebugType>full<\\/DebugType>
    <DebugSymbols>true<\\/DebugSymbols>
    <Optimize>false<\\/Optimize>
    <DefineConstants>TRACE;DEBUG;Development<\\/DefineConstants>
    <ErrorReport>prompt<\\/ErrorReport>
  <\\/PropertyGroup>
  <PropertyGroup Condition=\\\"'\\$\\(Configuration\\)'=='QualityCheck'\\\">
    <DebugType>portable<\\/DebugType>
    <DebugSymbols>true<\\/DebugSymbols>
    <Optimize>false<\\/Optimize>
    <DefineConstants>TRACE;QualityCheck<\\/DefineConstants>
    <ErrorReport>none<\\/ErrorReport>
  <\\/PropertyGroup>
  <PropertyGroup Condition=\\\"'\\$\\(Configuration\\)'=='Productive'\\\">
    <DebugType>portable<\\/DebugType>
    <DebugSymbols>true<\\/DebugSymbols>
    <Optimize>false<\\/Optimize>
    <DefineConstants>Productive<\\/DefineConstants>
    <ErrorReport>none<\\/ErrorReport>
  <\\/PropertyGroup>(\\n|.)*
<\\/Project>\\n?$"""
        result = self.__standardized_task_verify_standard_format_for_csproj_files(regex, csproj_file)
        return (result[0], regex, result[1])

    def __standardized_task_verify_standard_format_for_csproj_files(self, regex: str, csproj_file: str) -> tuple[bool, list[str]]:
        filename = os.path.basename(csproj_file)
        self._protected_sc.log.log(f"Check {filename}...",LogLevel.Debug)
        file_content = GeneralUtilities.read_text_from_file(csproj_file)
        regex_for_check = regex.replace("\r", GeneralUtilities.empty_string).replace("\n", "\\n")
        file_content = file_content.replace("\r", GeneralUtilities.empty_string)
        match = re.match(regex_for_check, file_content)
        result = match is not None
        hints = None
        if not result:
            hints = self.get_hints_for_csproj(regex, file_content)
        return (result, hints)

    @GeneralUtilities.check_arguments
    def get_hints_for_csproj(self, regex: str, file_content: str) -> list[str]:
        result: list[str] = []
        regex_lines = GeneralUtilities.string_to_lines(regex)
        file_content_lines = GeneralUtilities.string_to_lines(file_content)
        #amount_of_regexes = len(regex_lines)
        amount_of_lines = len(file_content_lines)
        if amount_of_lines< len(regex_lines):
            result.append("csproj-file has less lines than the regex requires.")
            return result
        for i in range(35):
            s = file_content_lines[i]
            r = regex_lines[i]
            if not re.match(r, s):
                result.append(f"Line {i+1} does not match: Regex='{r}' String='{s}'")
        return result

    @GeneralUtilities.check_arguments
    def generate_reference(self, generate_class_reference:bool=False) -> None:
        self.generate_reference_using_docfx(generate_class_reference)

    
    @GeneralUtilities.check_arguments
    def update_year_for_dotnet_codeunit(self) -> None:
        codeunit_folder:str=self.get_codeunit_folder()
        codeunit_name = os.path.basename(codeunit_folder)
        csproj_file = os.path.join(codeunit_folder, codeunit_name, f"{codeunit_name}.csproj")
        self._protected_sc.update_year_in_copyright_tags(csproj_file)
        csprojtests_file = os.path.join(codeunit_folder, f"{codeunit_name}Tests", f"{codeunit_name}Tests.csproj")
        self._protected_sc.update_year_in_copyright_tags(csprojtests_file)
        nuspec_file = os.path.join(codeunit_folder, "Other", "Build", f"{codeunit_name}.nuspec")
        if os.path.isfile(nuspec_file):
            self._protected_sc.update_year_in_copyright_tags(nuspec_file)
 
    @GeneralUtilities.check_arguments
    def run_testcases(self) -> None:
        self._protected_sc.log.log("Run testcases...")
        dotnet_build_configuration: str = self.get_target_environment_type()
        codeunit_name: str = self.get_codeunit_name()

        repository_folder: str = self.get_repository_folder().replace("\\", "/")
        coverage_file_folder = os.path.join(repository_folder, codeunit_name, "Other/Artifacts/TestCoverage")
        temp_folder = os.path.join(GeneralUtilities.get_temp_folder(), str(uuid.uuid4()))
        GeneralUtilities.ensure_directory_exists(temp_folder)
        runsettings_file = "runsettings.xml"
        codeunit_folder = f"{repository_folder}/{codeunit_name}"
        GeneralUtilities.ensure_directory_exists(coverage_file_folder)
        target_file = os.path.join(coverage_file_folder, "TestCoverage.xml")
        GeneralUtilities.ensure_file_does_not_exist(target_file)

        sln_file = os.path.join(codeunit_folder, f"{codeunit_name}.sln")
        args: list[str] = ["test", sln_file, "-c", dotnet_build_configuration, "-o", temp_folder]
        runsettings_path = os.path.join(codeunit_folder, runsettings_file)
        if os.path.isfile(runsettings_path):
            args += ["--settings", runsettings_path]
        # Write the test-results (test-binaries-deployment and coverage) into the system-temp-folder (a subfolder of
        # temp_folder) instead of a relative "./TestResults" inside the codeunit-folder. The relative path would otherwise
        # leave a folder behind in the codeunit-folder (visible e.g. when building inside the mounted Debian-build-container).
        # The whole temp_folder - including these results - is removed in the finally-block below.
        args += ["--results-directory", os.path.join(temp_folder, "TestResults")]
        # Run dotnet-test from an absolute working-directory (a subfolder of temp_folder) with node-reuse disabled, for the
        # same reason as in get_dotnet_build_diagnostics: building the solution with "-o" makes MSBuild create an additional
        # relative "tmp/<guid>"-output-folder, which a reused worker-node would otherwise create inside the codeunit-folder
        # where it can be left behind on a bind-mounted filesystem. All paths passed to dotnet-test are absolute, so the
        # changed working-directory does not affect the test-result or the coverage-output.
        test_working_directory = os.path.join(temp_folder, "WorkingDirectory")
        GeneralUtilities.ensure_directory_exists(test_working_directory)
        try:
            program_output=self._protected_sc.run_program_argsasarray("dotnet", args, test_working_directory, print_live_output=self.get_verbosity()==LogLevel.Debug, timeoutInSeconds=60*20, env_vars={"MSBUILDDISABLENODEREUSE": "1"})
            test_output:str=program_output[1]
            output_lines=program_output[1].split("\n")
            output_lines=[line for line in output_lines if GeneralUtilities.string_has_content(line)]
            generated_coverage_file: str = output_lines[-1].strip()#the cobertura file is printed in the end of the output by the xplat collector
            GeneralUtilities.assert_file_exists(generated_coverage_file)
            shutil.copyfile(generated_coverage_file, target_file)
        finally:
            GeneralUtilities.ensure_directory_does_not_exist(temp_folder)

        self.__remove_unrelated_package_from_testcoverage_file(target_file, codeunit_name)
        root: etree._ElementTree = etree.parse(target_file)
        source_base_path_in_coverage_file: str = root.xpath("//coverage/sources/source/text()")[0].replace("\\", "/")
        content = GeneralUtilities.read_text_from_file(target_file)
        GeneralUtilities.assert_condition(source_base_path_in_coverage_file.startswith(repository_folder) or repository_folder.startswith(source_base_path_in_coverage_file), f"Unexpected path for coverage. Sourcepath: \"{source_base_path_in_coverage_file}\"; repository: \"{repository_folder}\"")
        content = re.sub('\\\\', '/', content)
        content = re.sub("filename=\"([^\"]+)\"", lambda match: self.__standardized_tasks_run_testcases_for_dotnet_project_helper(source_base_path_in_coverage_file, codeunit_folder, match), content)
        GeneralUtilities.write_text_to_file(target_file, content)
        self.run_testcases_common_post_task(repository_folder, codeunit_name, True, self.get_target_environment_type())
        artifacts_folder = os.path.join(repository_folder, codeunit_name, "Other", "Artifacts")
        for subfolder in GeneralUtilities.get_direct_folders_of_folder(artifacts_folder):
            if os.path.basename(subfolder).startswith("BuildResultTests_DotNet_"):
                GeneralUtilities.ensure_directory_does_not_exist(subfolder)

        amount_of_ignored_testcases:int=self.__get_amount_of_ignored_testcases(test_output)
        project_has_ignored_testcases:bool=0<amount_of_ignored_testcases
        if project_has_ignored_testcases:
            raise ValueError(f"Project '{codeunit_name}' has {amount_of_ignored_testcases} ignored testcases.", LogLevel.Warning)

    @GeneralUtilities.check_arguments
    def __get_amount_of_ignored_testcases(self, test_output: str) -> int:
        # Ignored (=skipped) testcases are counted in the summary-line which dotnet-test prints for each test-project.
        # The summary of the VSTest-runner looks like "Failed: 0, Passed: 3, Skipped: 1, Total: 4" and the summary of the
        # Microsoft-Testing-Platform-runner looks like "total: 4 / failed: 0 / succeeded: 3 / skipped: 1".
        result: int = 0
        for match in re.finditer(r"skipped:\s*(\d+)", test_output, re.IGNORECASE):
            result = result+int(match.group(1))
        return result
    
    @GeneralUtilities.check_arguments
    def __remove_unrelated_package_from_testcoverage_file(self, file: str, codeunit_name: str) -> None:
        root: etree._ElementTree = etree.parse(file)
        packages = root.xpath('//coverage/packages/package')
        for package in packages:
            if package.attrib['name'] != codeunit_name:
                package.getparent().remove(package)
        result = etree.tostring(root).decode("utf-8")
        GeneralUtilities.write_text_to_file(file, result)


    @GeneralUtilities.check_arguments
    def __standardized_tasks_run_testcases_for_dotnet_project_helper(self, source: str, codeunit_folder: str, match: re.Match) -> str:
        filename = match.group(1)
        file = os.path.join(source, filename)
        GeneralUtilities.assert_condition(file.startswith(codeunit_folder), f"Unexpected path for coverage-file. File: \"{file}\"; codeunitfolder: \"{codeunit_folder}\"")
        filename_relative = f".{file[len(codeunit_folder):]}"
        return f'filename="{filename_relative}"'

    
    def get_dependencies(self)->dict[str,set[str]]:
        return dict[str,set[str]]()#TODO
    
    @GeneralUtilities.check_arguments
    def get_available_versions(self,dependencyname:str)->list[str]:
        return []#TODO

    def set_dependency_version(self,name:str,new_version:str)->None:
        raise ValueError(f"Operation is not implemented.")
        #self.update_year_for_dotnet_codeunit()
        #csproj_file:str=os.path.join(self.get_codeunit_folder(), self.get_codeunit_name(), self.get_codeunit_name() + ".csproj")
        #self._protected_sc.update_dependencies_of_dotnet_project(csproj_file,[])#TODO set ignored codeunits
    

class TFCPS_CodeUnitSpecific_DotNet_CLI:

    @staticmethod
    @GeneralUtilities.check_arguments
    def parse(file:str)->TFCPS_CodeUnitSpecific_DotNet_Functions:
        parser=TFCPS_CodeUnitSpecific_Base_CLI.get_base_parser()
        #add custom parameter if desired
        args=parser.parse_args()
        result:TFCPS_CodeUnitSpecific_DotNet_Functions=TFCPS_CodeUnitSpecific_DotNet_Functions(file,LogLevel(int(args.verbosity)),args.targetenvironmenttype,not args.nocache,args.ispremerge)
        return result 
