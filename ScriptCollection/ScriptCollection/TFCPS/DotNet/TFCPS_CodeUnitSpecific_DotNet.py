import os
import re
import shutil
import uuid
import json
from lxml import etree
import yaml
from .CertificateGeneratorInformationBase import CertificateGeneratorInformationBase
from ...GeneralUtilities import GeneralUtilities
from ...SCLog import  LogLevel
from ..PackageSource import PackageSource
from ..TFCPS_CodeUnitSpecific_Base import TFCPS_CodeUnitSpecific_Base,TFCPS_CodeUnitSpecific_Base_CLI

class TFCPS_CodeUnitSpecific_DotNet_Functions(TFCPS_CodeUnitSpecific_Base):
 
    is_library:bool = None
    csproj_file:bool = None
    #the output of the dotnet-cli is localized. The language is set explicitly for the commands whose output gets parsed, because otherwise the parsing would only work on machines which are configured to use english.
    __dotnet_cli_environment_variables:dict = {"DOTNET_CLI_UI_LANGUAGE": "en-US"}
    #the only accepted form of a version of a package-reference: an exact version in square brackets. Everything else is a version-range.
    __pinned_version_regex = re.compile(r"^\[[^,\[\]]+\]$")

    def __init__(self,current_file:str,verbosity:LogLevel,targetenvironmenttype:str,use_cache:bool,is_pre_merge:bool):
        super().__init__(current_file, verbosity,targetenvironmenttype,use_cache,is_pre_merge)
        self.csproj_file=os.path.join(self.get_codeunit_folder(), self.get_codeunit_name(), self.get_codeunit_name() + ".csproj")
        self.is_library="<OutputType>Library</OutputType>" in GeneralUtilities.read_text_from_file(self.csproj_file)#TODO do a real check by checking this property using xpath
        #every dotnet-operation of a codeunit (build, test, linting, ...) restores the dependencies of the codeunit, so the sources
        #they are downloaded from have to be available for all of them and not only for the build.
        self.__ensure_declared_package_sources_are_available()

    @GeneralUtilities.check_arguments
    def __ensure_declared_package_sources_are_available(self) -> None:
        """Ensures that every NuGet-source which is declared for this machine (see TFCPS_Tools_General.get_declared_package_sources) is
        registered with its current credentials, so a codeunit can also use dependencies which are not available on nuget.org.
        A source which is already registered under the declared name is removed and registered again, so an outdated registration (for
        example one which points to another url) can not let the registration fail. Sources which are not declared are not touched at
        all: the registration is stored in the NuGet-configuration of the current user, which - when the build runs directly on the
        host - is the configuration the user also uses for their own work and which must not be destroyed by a build."""
        package_sources: list[PackageSource] = self.tfcps_Tools_General.get_declared_package_sources("CSharp")
        if len(package_sources) == 0:
            return
        codeunit_folder: str = self.get_codeunit_folder()
        for package_source in package_sources:
            registered_sources: dict[str, str] = self.__get_registered_nuget_sources(codeunit_folder)
            name_of_source_with_same_name: str = None
            name_of_source_with_same_url: str = None
            for registered_name, registered_url in registered_sources.items():
                if registered_name.lower() == package_source.name.lower():
                    name_of_source_with_same_name = registered_name
                elif self.__nuget_sources_are_equal(registered_url, package_source.url):
                    #the same feed can already be registered under another name (which is the usual case on a machine on which the user
                    #configured the feed manually). Such a source is updated instead of being added a second time, because a second
                    #registration of the same url would let every restore query the feed twice.
                    name_of_source_with_same_url = registered_name
            if name_of_source_with_same_name is not None:
                self.__remove_nuget_source(codeunit_folder, name_of_source_with_same_name)
            if name_of_source_with_same_url is None:
                arguments = ["nuget", "add", "source", package_source.url, "--name", package_source.name]
            else:
                #the credentials are set again even when the source already exists, because a token can have been rotated since it was registered.
                arguments = ["nuget", "update", "source", name_of_source_with_same_url, "--source", package_source.url]
            if package_source.has_credentials():
                arguments = arguments+["--username", package_source.username, "--password", package_source.password]
                if not GeneralUtilities.current_system_is_windows():
                    #without this the password can not be encrypted, which lets the command fail on the operating-systems which do not support the encryption.
                    arguments.append("--store-password-in-clear-text")
            arguments_for_log = list(arguments)
            if package_source.has_credentials():
                arguments_for_log[arguments_for_log.index(package_source.password)] = "***"#the password must not be written to the build-log
            self._protected_sc.log.log(f"Add NuGet-source \"{package_source.name}\" ({package_source.url})..." if name_of_source_with_same_url is None else f"Update the already registered NuGet-source \"{name_of_source_with_same_url}\" ({package_source.url})...", LogLevel.Debug)
            self._protected_sc.run_program_argsasarray("dotnet", arguments, codeunit_folder, arguments_for_log=arguments_for_log, print_live_output=False, env_vars=self.__dotnet_cli_environment_variables)

    @GeneralUtilities.check_arguments
    def __remove_nuget_source(self, folder: str, name: str) -> None:
        """Removes the registration of the NuGet-source with the given name, so it can be registered again with its currently declared url and credentials."""
        self._protected_sc.log.log(f"Remove the outdated registration of the NuGet-source \"{name}\"...", LogLevel.Debug)
        self._protected_sc.run_program_argsasarray("dotnet", ["nuget", "remove", "source", name], folder, print_live_output=False, env_vars=self.__dotnet_cli_environment_variables)

    @GeneralUtilities.check_arguments
    def __get_registered_nuget_sources(self, folder: str) -> dict[str, str]:
        """Returns the NuGet-sources which are registered for the given folder as a mapping of their name to their url. The sources are
        read from the output of "dotnet nuget list source", which prints the name (with its state) and the url of a source in two
        consecutive lines."""
        result: dict[str, str] = {}
        list_result = self._protected_sc.run_program_argsasarray("dotnet", ["nuget", "list", "source"], folder, throw_exception_if_exitcode_is_not_zero=False, print_live_output=False, env_vars=self.__dotnet_cli_environment_variables)
        name_pattern = re.compile(r"^\s*\d+\.\s+(.+?)\s+\[[^\[\]]+\]\s*$")
        current_name: str = None
        for line in list_result[1].splitlines():
            match = name_pattern.match(line)
            if match is not None:
                current_name = match.group(1).strip()
            elif current_name is not None and GeneralUtilities.string_has_content(line):
                result[current_name] = line.strip()
                current_name = None
        return result

    @GeneralUtilities.check_arguments
    def __nuget_sources_are_equal(self, url: str, other_url: str) -> bool:
        """Compares two urls of package-sources. A trailing slash and the case are ignored because they do not address a different feed."""
        return url.strip().rstrip("/").lower() == other_url.strip().rstrip("/").lower()

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
    def __get_lock_file_name(self, runtime: str) -> str:
        """Returns the name of the lock-file which belongs to the given runtime.

        Every runtime needs its own lock-file: the lock-file records the set of runtime-identifiers it was created for, and a
        restore in locked mode fails with NU1004 when that set differs from the one which is currently restored (the restore
        gets exactly one runtime via "--runtime"). The name is relative, so NuGet resolves it per project - a restore over the
        solution therefore creates one lock-file next to each of the two project-files instead of letting them collide."""
        return f"packages.{runtime}.lock.json"

    @GeneralUtilities.check_arguments
    def __get_lock_file_arguments(self, codeunit_folder: str, codeunit_name: str, runtime: str) -> list[str]:
        """Returns the restore-arguments which pin the dependencies of the given runtime to the content of its lock-files.

        Locked mode is only requested when the lock-file of every project of the codeunit already exists, because a restore in
        locked mode can not create one. A codeunit which does not have them yet is restored without it and gets a warning, so
        introducing the lock-files does not break the build of a codeunit which was not migrated yet."""
        lock_file_name: str = self.__get_lock_file_name(runtime)
        expected_lock_files: list[str] = [os.path.join(codeunit_folder, project_name, lock_file_name) for project_name in [codeunit_name, codeunit_name+"Tests"]]
        missing_lock_files: list[str] = [lock_file for lock_file in expected_lock_files if not os.path.isfile(lock_file)]
        result: list[str] = [f"-p:NuGetLockFilePath={lock_file_name}"]
        if len(missing_lock_files) == 0:
            result.append("--locked-mode")
        else:
            self._protected_sc.log.log(f"The dependencies of codeunit \"{codeunit_name}\" are not restored in locked mode for the runtime \"{runtime}\", because the following lock-file(s) do not exist yet: {', '.join(missing_lock_files)}. The restore creates them now; commit them so that the dependencies of this codeunit are pinned.", LogLevel.Warning)
        return result

    @GeneralUtilities.check_arguments
    def __get_arguments_which_prevent_writing_a_lock_file(self) -> list[str]:
        """Returns the arguments which keep a dotnet-operation from writing a lock-file into the codeunit.

        The lock-files belong to the restore of the build alone, because only there the runtime - and with it the name of the
        lock-file which belongs to that runtime - is known. Every other dotnet-operation of a codeunit (linting, test, ...)
        works on the solution instead of on one runtime and restores implicitly, and the csproj-property
        "RestorePackagesWithLockFile" would make each of those restores write a lock-file under the default-name next to the
        runtime-specific ones.
        The lock-file of those operations is therefore pointed at a throwaway-path outside of the repository. Switching the
        property off instead does not work: nuget rejects a restore with NU1005 as soon as a lock-file under the default-name
        exists, which is exactly the case this has to survive (a developer who ran "dotnet build" once has such a file). The
        value has to be passed on the command-line, because a property which the project-file sets explicitly wins over one
        which comes from the environment."""
        return [f"-p:NuGetLockFilePath={self.tfcps_Tools_General.get_throwaway_lock_file(self.get_codeunit_name())}"]

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
            self._protected_sc.run_program_argsasarray("dotnet", ["restore", "--runtime", runtime]+self.__get_lock_file_arguments(codeunit_folder, codeunit_name, runtime), codeunit_folder,print_live_output=self.get_verbosity()==LogLevel.Debug)
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
            # The lock-file of this runtime becomes a part of the build-result: it states which version of which package
            # the build actually used, which is what makes it possible to reproduce a build later or to check an
            # artifact against a vulnerability afterwards. The working-copy keeps its own lock-file, so this is a copy
            # and not a move.
            # It is copied into a folder per project, because the name of the file only contains the runtime while a
            # codeunit builds more than one project (itself and its test-project) for the same runtime, so a flat folder
            # would let the second project overwrite the file of the first one. The name of the file itself stays
            # unchanged, because it is the name nuget expects and a consumer of the artifact reads the runtime from it.
            lock_file = os.path.join(csproj_file_folder, self.__get_lock_file_name(runtime))
            if os.path.isfile(lock_file):
                lock_file_folder_target = os.path.join(codeunit_folder, "Other", "Artifacts", "PackagesLock", csproj_file_name_without_extension)
                GeneralUtilities.ensure_directory_exists(lock_file_folder_target)
                lock_file_target = os.path.join(lock_file_folder_target, os.path.basename(lock_file))
                GeneralUtilities.ensure_file_does_not_exist(lock_file_target)
                shutil.copyfile(lock_file, lock_file_target)
            else:
                # The restore which ran above creates the file whenever the project demands one (see
                # __get_lock_file_arguments), so a missing file means the project does not set
                # RestorePackagesWithLockFile - and then the build-result does not state which versions it used.
                self._protected_sc.log.log(f"The lock-file \"{lock_file}\" does not exist, so the build-result of \"{csproj_file_name_without_extension}\" does not contain the versions which were used for the runtime \"{runtime}\".", LogLevel.Warning)

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
        
        files_to_sign: dict[str, str] = self.get_filestosign_from_commandline_arguments(dict())
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
        nuspec_file = os.path.join(build_folder, f"{codeunitname}.nuspec")
        root: etree._ElementTree = etree.parse(nuspec_file)
        # the elements are matched by their local name because the nuspec-namespace can be declared as default-namespace
        # (<package xmlns="...">) as well as with a prefix (<ns0:package xmlns:ns0="...">) and both variants are valid.
        versions = root.xpath("//*[local-name() = 'package']/*[local-name() = 'metadata']/*[local-name() = 'version']/text()")
        if len(versions) == 0:
            raise ValueError(f"Can not determine the version because there is no version-element in \"{nuspec_file}\".")
        current_version = versions[0]
        nupkg_filename = f"{codeunitname}.{current_version}.nupkg"
        nupkg_file = f"{build_folder}/{nupkg_filename}"
        GeneralUtilities.ensure_file_does_not_exist(nupkg_file)
        commit_id = self._protected_sc.git_get_commit_id(repository_folder)
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
        # "-dpr" keeps CycloneDX from restoring the project itself. The SBOM is generated directly after the project and its
        # test-project were built, so the dependencies are restored and the assets-file CycloneDX reads is up-to-date already.
        # Its restore would also not be able to name the lock-file of the runtime the build used, so it would write one under
        # the default-name (see __get_arguments_which_prevent_writing_a_lock_file).
        self._protected_sc.run_program_argsasarray("dotnet", ["CycloneDX", f"{codeunit_name}/{codeunit_name}.csproj", "-o", bomfile_folder, "-dpr"], codeunit_folder)
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
            # The arguments are passed as an array and without quoting them by hand: run_program splits its
            # argument-string with GeneralUtilities.arguments_to_array, which splits at spaces without interpreting
            # quotes, so hand-written quotes end up as part of the argument-value. The value of "-o" would therefore
            # become '"<temp_output_folder>"' (with the quotes), which MSBuild treats as a relative path (it does not
            # begin with a drive-letter anymore) and resolves against the working-directory, so it writes to a path
            # which contains a quote in the middle. On Linux that only creates a strangely named folder, on Windows a
            # quote is not allowed in a path and the msbuild-task GenerateDepsFile fails with an IOException.
            run_result = self._protected_sc.run_program_argsasarray("dotnet", ["build", sln_file, "-nologo", "-v", "minimal", "-o", temp_output_folder]+self.__get_arguments_which_prevent_writing_a_lock_file(), temp_output_folder, throw_exception_if_exitcode_is_not_zero=False, env_vars={"DOTNET_CLI_UI_LANGUAGE": "en-US", "MSBUILDDISABLENODEREUSE": "1"})
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
        self._protected_sc.normalize_invisible_characters_of_files_in_folder(codeunit_folder, ["cs"])
        nuspec_file = os.path.join(codeunit_folder, "Other", "Build", f"{codeunit_name}.nuspec")
        if os.path.isfile(nuspec_file):
            self._protected_sc.format_xml_file(nuspec_file)
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
        self.update_year_for_dotnet_codeunit()
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
        self.__verify_that_all_package_references_are_pinned(csproj_file)

        test_csproj_project_name = csproj_project_name+"Tests"
        test_csproj_file = os.path.join(codeunit_folder, test_csproj_project_name, test_csproj_project_name+".csproj")
        result2: tuple[bool, str, list[str]] = self.__standardized_task_verify_standard_format_for_test_csproj_file(test_csproj_file, codeunit_name, codeunit_version)
        if not result2[0]:
            hints: str = "\n".join(result2[2])
            raise ValueError(f"'{test_csproj_file}' with content '{GeneralUtilities.read_text_from_file(test_csproj_file)}' does not match the standardized .csproj-file-format which is defined by the regex '{result2[1]}'.\n{hints}")
        self.__check_csproj_urls(test_csproj_file)
        self.__verify_that_all_package_references_are_pinned(test_csproj_file)

    @GeneralUtilities.check_arguments
    def __verify_that_all_package_references_are_pinned(self, csproj_file: str) -> None:
        """Ensures that every package-reference of the given project is pinned to exactly one version.

        The version-attribute of a package-reference is a version-*range*, not a version: "1.2.3" means "at least 1.2.3".
        NuGet resolves such a range to the lowest version which satisfies it - or, when exactly that version is not available
        on the feed (unlisted, removed, incomplete mirror), silently to the next higher one. "[1.2.3]" means exactly 1.2.3,
        so a version which is not available fails loudly instead of becoming a different version than the one which is
        written in the project-file. This keeps the restore deterministic and makes the version which is deployed readable
        from the source-code."""
        root: etree._ElementTree = etree.parse(csproj_file)
        not_pinned: list[str] = []
        for package_reference in root.xpath("//PackageReference"):
            #the attributes are read case-insensitively because msbuild reads them that way: a "version"-attribute is as
            #effective as a "Version"-attribute, so a case-sensitive check would report a version which exists as missing.
            attributes: dict[str, str] = {name.lower(): value for name, value in package_reference.attrib.items()}
            package_name: str = attributes.get("include") or attributes.get("update") or "(package-reference without a name)"
            if 0 < len(package_reference.xpath("*[translate(local-name(),'VERSION','version')='version']")):
                not_pinned.append(f"{package_name}: the version is set as child-element; it must be set as attribute in the form Version=\"[<version>]\".")
                continue
            version: str = attributes.get("version")
            if version is None:
                not_pinned.append(f"{package_name}: no version is set at all, so the restore decides which version is used.")
            elif self.__pinned_version_regex.match(version.strip()) is None:
                not_pinned.append(f"{package_name}: the version \"{version}\" is a version-range, not a pinned version. Pin it in the form Version=\"[<version>]\".")
        if 0 < len(not_pinned):
            raise ValueError(f"The following package-reference(s) in \"{csproj_file}\" are not pinned to exactly one version:\n" + "\n".join(f"  {entry}" for entry in not_pinned))

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
    <RestorePackagesWithLockFile>true<\\/RestorePackagesWithLockFile>
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
    <RestorePackagesWithLockFile>true<\\/RestorePackagesWithLockFile>
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
        amount_of_lines = len(file_content_lines)
        if amount_of_lines< len(regex_lines):
            result.append("csproj-file has less lines than the regex requires.")
            return result
        for i in range(35):#you can do this check only for the first 35 lines
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
    def run_testcases(self, timeoutInSeconds:int=60*30) -> None:
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
        args: list[str] = ["test", sln_file, "-c", dotnet_build_configuration, "-o", temp_folder]+self.__get_arguments_which_prevent_writing_a_lock_file()
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
            program_output=self._protected_sc.run_program_argsasarray("dotnet", args, test_working_directory, print_live_output=self.get_verbosity()==LogLevel.Debug, timeoutInSeconds=timeoutInSeconds, env_vars={"MSBUILDDISABLENODEREUSE": "1"})
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
            self._protected_sc.log.log(f"Project '{codeunit_name}' has {amount_of_ignored_testcases} ignored testcases.", LogLevel.Warning)

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
