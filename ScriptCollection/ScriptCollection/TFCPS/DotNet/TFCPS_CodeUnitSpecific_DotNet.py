import os
import re
import shutil
import tempfile
import uuid
import json
from lxml import etree
import yaml
from .CertificateGeneratorInformationBase import CertificateGeneratorInformationBase
from ...GeneralUtilities import GeneralUtilities
from ...SCLog import  LogLevel
from ..TFCPS_CodeUnitSpecific_Base import TFCPS_CodeUnitSpecific_Base,TFCPS_CodeUnitSpecific_Base_CLI

class TFCPS_CodeUnitSpecific_DotNet_Functions(TFCPS_CodeUnitSpecific_Base):
 
    is_library:bool
    csproj_file:bool

    def __init__(self,current_file:str,verbosity:LogLevel,targetenvironmenttype:str,use_cache:bool,is_pre_merge:bool):
        super().__init__(current_file, verbosity,targetenvironmenttype,use_cache,is_pre_merge)
        self.csproj_file=os.path.join(self.get_codeunit_folder(), self.get_codeunit_name(), self.get_codeunit_name() + ".csproj")
        self.is_library="<OutputType>Library</OutputType>" in GeneralUtilities.read_text_from_file(self.csproj_file)#TODO do a real check by checking this property using xpath

    @GeneralUtilities.check_arguments
    def build(self,runtimes:list[str],generate_open_api_spec:bool) -> None:
        if self.is_library:
            self.standardized_tasks_build_for_dotnet_library_project(runtimes)
            GeneralUtilities.assert_condition(not generate_open_api_spec,"OpenAPI-Specification can not be generated for a library.")
        else:
            self.standardized_tasks_build_for_dotnet_project(runtimes)
            if generate_open_api_spec:
                self.generate_openapi_file(runtimes[0])

    @GeneralUtilities.check_arguments
    def generate_openapi_file(self, runtime: str) -> None:
        swagger_document_name: str = "APISpecification"
        self._protected_sc.log.log("Generate OpenAPI-specification-file...")
        codeunitname =self.get_codeunit_name()
        repository_folder =self.get_repository_folder()
        codeunit_folder = os.path.join(repository_folder, codeunitname)
        artifacts_folder = os.path.join(codeunit_folder, "Other", "Artifacts")
        GeneralUtilities.ensure_directory_exists(os.path.join(artifacts_folder, "APISpecification"))
        codeunit_version = self.tfcps_Tools_General.get_version_of_codeunit(os.path.join(codeunit_folder,f"{codeunitname}.codeunit.xml"))

        versioned_api_spec_file = f"APISpecification/{codeunitname}.v{codeunit_version}.api.json"
        self._protected_sc.run_program("swagger", f"tofile --output {versioned_api_spec_file} BuildResult_DotNet_{runtime}/{codeunitname}.dll {swagger_document_name}", artifacts_folder,print_live_output=self.get_verbosity()==LogLevel.Debug)
        api_file: str = os.path.join(artifacts_folder, versioned_api_spec_file)
        shutil.copyfile(api_file, os.path.join(artifacts_folder, f"APISpecification/{codeunitname}.latest.api.json"))

        resources_folder = os.path.join(codeunit_folder, "Other", "Resources")
        GeneralUtilities.ensure_directory_exists(resources_folder)
        resources_apispec_folder = os.path.join(resources_folder, "APISpecification")
        GeneralUtilities.ensure_directory_exists(resources_apispec_folder)
        resource_target_file = os.path.join(resources_apispec_folder, f"{codeunitname}.api.json")
        GeneralUtilities.ensure_file_does_not_exist(resource_target_file)
        shutil.copyfile(api_file, resource_target_file)

        with open(api_file, encoding="utf-8") as api_file_content:
            reloaded_json = json.load(api_file_content)

            yamlfile1: str = str(os.path.join(artifacts_folder, f"APISpecification/{codeunitname}.v{codeunit_version}.api.yaml"))
            GeneralUtilities.ensure_file_does_not_exist(yamlfile1)
            GeneralUtilities.ensure_file_exists(yamlfile1)
            with open(yamlfile1, "w+", encoding="utf-8") as yamlfile:
                yaml.dump(reloaded_json, yamlfile, allow_unicode=True)
 
            yamlfile2: str = str(os.path.join(artifacts_folder, f"APISpecification/{codeunitname}.latest.api.yaml"))
            GeneralUtilities.ensure_file_does_not_exist(yamlfile2)
            shutil.copyfile(yamlfile1, yamlfile2)

            yamlfile3: str = str(os.path.join(resources_apispec_folder, f"{codeunitname}.api.yaml"))
            GeneralUtilities.ensure_file_does_not_exist(yamlfile3)
            shutil.copyfile(yamlfile1, yamlfile3)

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
            self._protected_sc.run_program("dotnet", "restore", codeunit_folder,print_live_output=self.get_verbosity()==LogLevel.Debug)
            self._protected_sc.run_program_argsasarray("dotnet", ["build", csproj_file_name, "-c", dotnet_build_configuration, "-o", outputfolder, "--runtime", runtime], csproj_file_folder,print_live_output=self.get_verbosity()==LogLevel.Debug)
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
        self._protected_sc.run_program("nuget", f"pack {codeunitname}.nuspec -Properties \"commitid={commit_id}\"", build_folder)
        GeneralUtilities.ensure_directory_does_not_exist(outputfolder)
        GeneralUtilities.ensure_directory_exists(outputfolder)
        os.rename(nupkg_file, f"{outputfolder}/{nupkg_filename}")

    @GeneralUtilities.check_arguments
    def generate_sbom_for_dotnet_project(self, codeunit_folder: str) -> None:
        self._protected_sc.log.log("Generate SBOM...")
        codeunit_name = os.path.basename(codeunit_folder)
        bomfile_folder = "Other\\Artifacts\\BOM"
        self._protected_sc.run_program_argsasarray("dotnet", ["CycloneDX", f"{codeunit_name}\\{codeunit_name}.csproj", "-o", bomfile_folder], codeunit_folder)
        codeunitversion = self.tfcps_Tools_General.get_version_of_codeunit(os.path.join(codeunit_folder, f"{codeunit_name}.codeunit.xml"))
        target = f"{codeunit_folder}\\{bomfile_folder}\\{codeunit_name}.{codeunitversion}.sbom.xml"
        GeneralUtilities.ensure_file_does_not_exist(target)
        os.rename(f"{codeunit_folder}\\{bomfile_folder}\\bom.xml", target)
        self._protected_sc.format_xml_file(target) 

    @GeneralUtilities.check_arguments
    def get_dotnet_build_diagnostics(self) -> list[tuple[LogLevel, str, str | None, int | None]]:
        codeunit_name = self.get_codeunit_name()
        codeunit_folder = self.get_codeunit_folder()
        sln_file = os.path.join(codeunit_folder, codeunit_name + ".sln")
        temp_output_folder = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        GeneralUtilities.ensure_directory_exists(temp_output_folder)
        try:
            run_result = self._protected_sc.run_program("dotnet", f"build \"{sln_file}\" -nologo -v minimal -o \"{temp_output_folder}\"", codeunit_folder, throw_exception_if_exitcode_is_not_zero=False)
        finally:
            GeneralUtilities.ensure_directory_does_not_exist(temp_output_folder)
        diagnostics: list[tuple[LogLevel, str, str | None, int | None]] = []
        pattern = re.compile(r"^\s*(?:(.+?)\((\d+),\d+\): )?(error|warning|message|info) [^:]+: (.+?)(?:\s*\[.+\])?\s*$", re.IGNORECASE)
        #TODO fix this function. this does not work. fyi output looks like this:
        #E:\Data\Projects\GRYLibrary\GRYLibrary>dotnet build GRYLibrary.sln -nologo -v minimal
        #Restore succeeded with 11 warning(s) in 0,9s
        #    E:\Data\Projects\GRYLibrary\GRYLibrary\GRYLibrary\GRYLibrary.csproj : warning NU1510: PackageReference Microsoft.CSharp will not be pruned. Consider removing this package from your dependencies, as it is likely unnecessary.
        #    E:\Data\Projects\GRYLibrary\GRYLibrary\GRYLibraryTests\GRYLibraryTests.csproj : warning NU1510: PackageReference Microsoft.Win32.Registry will not be pruned. Consider removing this package from your dependencies, as it is likely unnecessary.
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
        self._protected_sc.format_xml_file(os.path.join(codeunit_folder, codeunit_name, codeunit_name + ".csproj"), add_xml_declaration=False)
        self._protected_sc.format_xml_file(os.path.join(codeunit_folder, codeunit_name + "Tests", codeunit_name + "Tests.csproj"), add_xml_declaration=False)
        self.standardized_task_verify_standard_format_csproj_files()
        diagnostics = self.get_dotnet_build_diagnostics()
        has_errors = False
        for (level, message, file, line) in diagnostics:
            location = f" ({file}:{line})" if file else ""
            self._protected_sc.log.log(f"{message}{location}", level)
            if level == LogLevel.Error:#should not occurr on scbuildcodeunits because then the build would have failed already.
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

        test_csproj_project_name = csproj_project_name+"Tests"
        test_csproj_file = os.path.join(codeunit_folder, test_csproj_project_name, test_csproj_project_name+".csproj")
        result2: tuple[bool, str, list[str]] = self.__standardized_task_verify_standard_format_for_test_csproj_file(test_csproj_file, codeunit_name, codeunit_version)
        if not result2[0]:
            hints: str = "\n".join(result2[2])
            raise ValueError(f"'{test_csproj_file}' with content '{GeneralUtilities.read_text_from_file(test_csproj_file)}' does not match the standardized .csproj-file-format which is defined by the regex '{result2[1]}'.\n{hints}")

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
    def generate_reference(self) -> None:
        self.generate_reference_using_docfx()

    
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
        temp_folder = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        GeneralUtilities.ensure_directory_exists(temp_folder)
        runsettings_file = "runsettings.xml"
        codeunit_folder = f"{repository_folder}/{codeunit_name}"
        GeneralUtilities.ensure_directory_exists(coverage_file_folder)
        target_file = os.path.join(coverage_file_folder, "TestCoverage.xml")
        GeneralUtilities.ensure_file_does_not_exist(target_file)

        args: list[str] = ["test", f"{codeunit_name}.sln", "-c", dotnet_build_configuration]
        if os.path.isfile(os.path.join(codeunit_folder, runsettings_file)):
            args += ["--settings", runsettings_file]
        args += ["--results-directory","./TestResults"]
        program_output=self._protected_sc.run_program_argsasarray("dotnet", args, codeunit_folder, print_live_output=self.get_verbosity()==LogLevel.Debug, timeoutInSeconds=60*20)
        output_lines=program_output[1].split("\n")
        output_lines=[line for line in output_lines if GeneralUtilities.string_has_content(line)]
        generated_coverage_file: str = output_lines[-1].strip()#the cobertura file is printed in the end of the output by the xplat collector
        GeneralUtilities.assert_file_exists(generated_coverage_file)
        shutil.copyfile(generated_coverage_file, target_file)

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
    def __coverage_file_contains_sources_and_packages(self, file: str) -> bool:
        root: etree._ElementTree = etree.parse(file)
        sources = root.xpath("//coverage/sources/source/text()")
        packages = root.xpath("//coverage/packages/package")
        return len(sources) > 0 and len(packages) > 0

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
