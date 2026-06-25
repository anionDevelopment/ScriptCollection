import os
from pathlib import Path
import shutil
import re
import json
import argparse
from abc import ABC, abstractmethod
import xmlschema
from packaging.version import Version
from lxml import etree
from ..GeneralUtilities import GeneralUtilities, VersionEcholon
from ..ScriptCollectionCore import ScriptCollectionCore
from ..SCLog import  LogLevel
from .TFCPS_Tools_General import TFCPS_Tools_General
from .TFCPS_RemoteBuild import TFCPS_RemoteBuild, RunnerOperatingSystem



class TFCPS_CodeUnitSpecific_Base(ABC):

    __current_file:str=None
    __target_environment_type:str = None
    __repository_folder:str=None
    __codeunit_folder:str=None
    __current_folder:str=None
    __verbosity:LogLevel=None
    __use_cache:bool=None
    tfcps_Tools_General:TFCPS_Tools_General = None
    _protected_sc:ScriptCollectionCore = None
    __is_pre_merge:bool=False#TODO must be setable to true
    __validate_developers_of_repository:bool=True#TODO must be setable to false

    def __init__(self,current_file:str,verbosity:LogLevel,target_envionment_type:str,use_cache:bool,is_pre_merge:bool):
        self.__verbosity=verbosity
        self.__use_cache=use_cache
        self.__target_environment_type=target_envionment_type
        self.__current_file = str(Path(current_file).absolute())
        self.__current_folder = os.path.dirname(self.__current_file)
        self.__codeunit_folder=self.__search_codeunit_folder()
        self.__is_pre_merge=is_pre_merge
        self._protected_sc=ScriptCollectionCore()
        self._protected_sc.log.loglevel=self.__verbosity
        self.tfcps_Tools_General=TFCPS_Tools_General(self._protected_sc)
        self.tfcps_Tools_General.assert_is_codeunit_folder(self.__codeunit_folder)
        self.__repository_folder=GeneralUtilities.resolve_relative_path("..",self.__codeunit_folder)
        self._protected_sc.assert_is_git_repository(self.__repository_folder)

    def __search_codeunit_folder(self)->str:
        current_path:str=os.path.dirname(self.__current_file)
        enabled:bool=True
        while enabled:
            try:
                current_path=GeneralUtilities.resolve_relative_path("..",current_path)
                foldername=os.path.basename(current_path)
                codeunit_file:str=os.path.join(current_path,f"{foldername}.codeunit.xml")
                if os.path.isfile(codeunit_file):
                    return current_path
            except:
                enabled=False
        raise ValueError(f"Can not find codeunit-folder for folder \"{self.__current_file}\".")

    @abstractmethod
    def get_dependencies(self)->dict[str,set[str]]:
        raise ValueError(f"Operation is abstract.")

    @abstractmethod
    def get_available_versions(self,dependencyname:str)->list[str]:
        raise ValueError(f"Operation is abstract.")
    
    @abstractmethod
    def set_dependency_version(self,name:str,new_version:str)->None:
        raise ValueError(f"Operation is abstract.")

    def update_dependencies(self):
        self.update_dependencies_with_specific_echolon(VersionEcholon.LatestPatchOrLatestMinor)

    def update_dependencies_with_specific_echolon(self, echolon: VersionEcholon):
        ignored_dependencies=self.tfcps_Tools_General.get_dependencies_which_are_ignored_from_updates(self.get_codeunit_folder())
        for ignored_dependency in ignored_dependencies:
            self._protected_sc.log.log(f"Codeunit {self.get_codeunit_name()} ignores the dependency {ignored_dependency} in update-checks.", LogLevel.Warning)

        dependencies_dict:dict[str,set[str]]=self.get_dependencies()
        for dependencyname,dependency_versions in dependencies_dict.items():
            GeneralUtilities.assert_condition(0<len(dependency_versions),f"Dependency {dependencyname} is not used.")
            GeneralUtilities.assert_condition(len(dependency_versions)<2,f"Dependency {dependencyname} is used {len(dependency_versions)} times. Please consolidate it to one version before updating.")
            dependency_version=next(iter(dependency_versions))
            latest_currently_used_version=dependency_version
            if dependencyname not in ignored_dependencies: 
                try:
                    available_versions:list[str]=self.get_available_versions(dependencyname)
                    for available_version in available_versions:
                        GeneralUtilities.assert_condition(re.match(r"^(\d+).(\d+).(\d+)$", available_version) is not None,f"Invalid-version-string: {available_version}")
                    desired_version=GeneralUtilities.choose_version(available_versions,latest_currently_used_version,echolon)
                    GeneralUtilities.assert_condition(Version(dependency_version)<=Version(desired_version),f"Desired version {desired_version} for dependency {dependencyname} is less than the actual used version {latest_currently_used_version}.")
                    update_dependency:bool=desired_version!=latest_currently_used_version
                    if update_dependency:
                        if len(dependency_versions)==1:
                            GeneralUtilities.write_message_to_stdout("Update dependency "+dependencyname+" (which is currently used in version "+dependency_version+") to version "+desired_version+".")
                        self.set_dependency_version(dependencyname,desired_version)
                except Exception:
                    GeneralUtilities.write_message_to_stderr(f"Error while updating {dependencyname}.")
                    raise

    def get_version_of_project(self)->str:
        return self.tfcps_Tools_General.get_version_of_project(self.get_repository_folder())

    @GeneralUtilities.check_arguments
    def do_common_tasks_base(self,current_codeunit_version:str):
        repository_folder: str =self.get_repository_folder()
        self._protected_sc.assert_is_git_repository(repository_folder)
        codeunit_name: str = self.get_codeunit_name()
        project_version = self.tfcps_Tools_General.get_version_of_project(repository_folder)
        if current_codeunit_version is None:
            current_codeunit_version=project_version
        codeunit_folder = os.path.join(repository_folder, codeunit_name)

        # check codeunit-conformity
        # TODO check if foldername=="<codeunitname>[.codeunit.xml]" == <codeunitname> in file
        supported_codeunitspecificationversion = "2.9.4"  # should always be the latest version of the ProjectTemplates-repository
        codeunit_file = os.path.join(codeunit_folder, f"{codeunit_name}.codeunit.xml")
        if not os.path.isfile(codeunit_file):
            raise ValueError(f'Codeunitfile "{codeunit_file}" does not exist.')
        # TODO implement usage of self.reference_latest_version_of_xsd_when_generating_xml
        namespaces = {'cps': 'https://projects.aniondev.de/PublicProjects/Common/ProjectTemplates/-/tree/main/Conventions/RepositoryStructure/CommonProjectStructure',  'xsi': 'http://www.w3.org/2001/XMLSchema-instance'}
        root: etree._ElementTree = etree.parse(codeunit_file)

        # check codeunit-spcecification-version
        try:
            codeunit_file_version = root.xpath('//cps:codeunit/@codeunitspecificationversion', namespaces=namespaces)[0]
            if codeunit_file_version != supported_codeunitspecificationversion:
                raise ValueError(f"ScriptCollection only supports processing codeunits with codeunit-specification-version={supported_codeunitspecificationversion}.")
            schemaLocation = root.xpath('//cps:codeunit/@xsi:schemaLocation', namespaces=namespaces)[0]
            xmlschema.validate(codeunit_file, schemaLocation)
            # TODO check if the properties codeunithastestablesourcecode, codeunithasupdatabledependencies, throwexceptionifcodeunitfilecannotbevalidated, developmentState and description exist and the values are valid
        except Exception as exception:
            self._protected_sc.log.log_exception(f'Codeunitfile "{codeunit_file}" can not be validated due to the following exception:', exception,LogLevel.Warning)

        # check codeunit-name
        codeunit_name_in_codeunit_file = root.xpath('//cps:codeunit/cps:name/text()', namespaces=namespaces)[0]
        if codeunit_name != codeunit_name_in_codeunit_file:
            raise ValueError(f"The folder-name ('{codeunit_name}') is not equal to the codeunit-name ('{codeunit_name_in_codeunit_file}').")

        # check owner-name
        codeunit_ownername_in_codeunit_file = self.tfcps_Tools_General. get_codeunit_owner_name(self.get_codeunit_file())
        GeneralUtilities.assert_condition(GeneralUtilities.string_has_content(codeunit_ownername_in_codeunit_file), "No valid name for codeunitowner given.")

        # check owner-emailaddress
        codeunit_owneremailaddress_in_codeunit_file = self.tfcps_Tools_General.get_codeunit_owner_emailaddress(self.get_codeunit_file())
        GeneralUtilities.assert_condition(GeneralUtilities.string_has_content(codeunit_owneremailaddress_in_codeunit_file), "No valid email-address for codeunitowner given.")

        # check development-state
        developmentstate = root.xpath('//cps:properties/@developmentstate', namespaces=namespaces)[0]
        developmentstate_active = "Active development"
        developmentstate_maintenance = "Maintenance-updates only"
        developmentstate_inactive = "Inactive"
        GeneralUtilities.assert_condition(developmentstate in (developmentstate_active, developmentstate_maintenance, developmentstate_inactive), f"Invalid development-state. Must be '{developmentstate_active}' or '{developmentstate_maintenance}' or '{developmentstate_inactive}' but was '{developmentstate}'.")

        # check for mandatory files
        files = ["Other/Build/Build.py", "Other/QualityCheck/Linting.py", "Other/Reference/GenerateReference.py"]
        if self.tfcps_Tools_General.codeunit_has_testable_sourcecode(self.get_codeunit_file()):
            # TODO check if the testsettings-section appears in the codeunit-file
            files.append("Other/QualityCheck/RunTestcases.py")
        if self.tfcps_Tools_General.codeunit_has_updatable_dependencies(self.get_codeunit_file()):
            # TODO check if the updatesettings-section appears in the codeunit-file
            files.append("Other/UpdateDependencies.py")
        for file in files:
            combined_file = os.path.join(codeunit_folder, file)
            if not os.path.isfile(combined_file):
                raise ValueError(f'The mandatory file "{file}" does not exist in the codeunit-folder.')

        if os.path.isfile(os.path.join(codeunit_folder, "requirements.txt")):
            self.install_requirementstxt_for_codeunit()

        # check developer
        if self.__validate_developers_of_repository:
            expected_authors: list[tuple[str, str]] = []
            expected_authors_in_xml = root.xpath('//cps:codeunit/cps:developerteam/cps:developer', namespaces=namespaces)
            for expected_author in expected_authors_in_xml:
                author_name = expected_author.xpath('./cps:developername/text()', namespaces=namespaces)[0]
                author_emailaddress = expected_author.xpath('./cps:developeremailaddress/text()', namespaces=namespaces)[0]
                expected_authors.append((author_name, author_emailaddress)) 
            actual_authors: list[tuple[str, str]] = self.tfcps_Tools_General.get_all_authors_and_committers_of_repository(repository_folder, codeunit_name)
            # TODO refactor this check to only check commits which are behind this but which are not already on main
            # TODO verify also if the commit is signed by a valid key of the author
            for actual_author in actual_authors:
                if not (actual_author) in expected_authors:
                    actual_author_formatted = f"{actual_author[0]} <{actual_author[1]}>"
                    raise ValueError(f'Author/Comitter "{actual_author_formatted}" is not in the codeunit-developer-team. If {actual_author} is a authorized developer for this codeunit you should consider defining this in the codeunit-file or adapting the name using a .mailmap-file (see https://git-scm.com/docs/gitmailmap). The developer-team-check can also be disabled using the property validate_developers_of_repository.')

        dependent_codeunits = self.tfcps_Tools_General.get_dependent_code_units(codeunit_file)
        for dependent_codeunit in dependent_codeunits:
            if not self.tfcps_Tools_General.dependent_codeunit_exists(repository_folder, dependent_codeunit):
                raise ValueError(f"Codeunit {codeunit_name} does have dependent codeunit {dependent_codeunit} which does not exist.")

        # TODO implement cycle-check for dependent codeunits

        artifacts_folder = os.path.join(codeunit_folder, "Other", "Artifacts")
        GeneralUtilities.ensure_directory_does_not_exist(artifacts_folder)

        # get artifacts from dependent codeunits
        self.tfcps_Tools_General.copy_artifacts_from_dependent_code_units(repository_folder, codeunit_name)

        # update codeunit-version
        self.tfcps_Tools_General.write_version_to_codeunit_file(self.get_codeunit_file(), current_codeunit_version)
 
        # set project version
        package_json_file = os.path.join(repository_folder, "package.json")  # TDOO move this to a general project-specific (and codeunit-independent-script)
        if os.path.isfile(package_json_file):
            package_json_data: str = None
            with open(package_json_file, "r", encoding="utf-8") as f1:
                package_json_data = json.load(f1)
                package_json_data["version"] = project_version
            with open(package_json_file, "w", encoding="utf-8") as f2:
                json.dump(package_json_data, f2, indent=2)
            GeneralUtilities.write_text_to_file(package_json_file, GeneralUtilities.read_text_from_file(package_json_file).replace("\r", ""))

        # set default constants
        self.tfcps_Tools_General.set_default_constants(os.path.join(codeunit_folder))

        # Hints-file
        hints_file = os.path.join(codeunit_folder, "Other", "Reference", "ReferenceContent", "Hints.md")
        if not os.path.isfile(hints_file):
            raise ValueError(f"Hints-file '{hints_file}' does not exist.")

        # Copy license-file
        self.tfcps_Tools_General.copy_licence_file(self.get_codeunit_folder())

        # Propagate the repository-level dependency-version-pins (e.g. PlantUML, OpenAPIGenerator, JRE) into the codeunit
        # so each codeunit carries its own copy of the versions that are defined once at repository-level.
        repository_dependencies_folder = os.path.join(repository_folder, "Other", "Resources", "Dependencies")
        if os.path.isdir(repository_dependencies_folder):
            for dependency_folder in GeneralUtilities.get_direct_folders_of_folder(repository_dependencies_folder):
                dependency_name = os.path.basename(dependency_folder)
                source_version_file = os.path.join(dependency_folder, "Version.txt")
                target_version_file = os.path.join(codeunit_folder, "Other", "Resources", "Dependencies", dependency_name, "Version.txt")
                if os.path.isfile(target_version_file):# only update dependencies, do not create new ones automatically
                    GeneralUtilities.ensure_directory_exists(os.path.dirname(target_version_file))
                    shutil.copyfile(source_version_file, target_version_file)


    @GeneralUtilities.check_arguments
    def generate_reference_using_docfx(self):
        reference_folder =os.path.join( self.get_codeunit_folder(),"Other","Reference")
        generated_reference_folder = GeneralUtilities.resolve_relative_path("../Artifacts/Reference", reference_folder)
        GeneralUtilities.ensure_directory_does_not_exist(generated_reference_folder)
        GeneralUtilities.ensure_directory_exists(generated_reference_folder)
        obj_folder = os.path.join(reference_folder, "obj")
        GeneralUtilities.ensure_folder_exists_and_is_empty(obj_folder)
        self._protected_sc.run_program("docfx", "-t default,templates/darkfx docfx.json", reference_folder)
        GeneralUtilities.ensure_directory_does_not_exist(obj_folder)

    @GeneralUtilities.check_arguments
    def use_cache(self)->bool:
        return self.__use_cache

    @GeneralUtilities.check_arguments
    def run_program_on_remote_runner(self, required_os: RunnerOperatingSystem, program: str, arguments: list[str], working_directory: str) -> None:
        """Runs the given program for this codeunit on a remote task-runner that provides the given operating-system (see
        TFCPS_RemoteBuild and the SCTaskRunnerWindows/SCTaskRunnerMacOS-codeunits). This is used for operating-system-bound
        build-steps (e.g. flutter-windows- or flutter-ios-builds) which can not run on the current operating-system. After
        the runner finished, only the codeunit-folder is mirrored back into the local repository, so it looks as if the
        runner had built locally. working_directory must be a folder inside this codeunit."""
        TFCPS_RemoteBuild(self._protected_sc).run_program_on_runner(required_os, self.get_repository_folder(), self.get_codeunit_name(), program, arguments, working_directory)

    @GeneralUtilities.check_arguments
    def get_codeunit_folder(self)->str:
        return self.__codeunit_folder

    @GeneralUtilities.check_arguments
    def get_codeunit_name(self)->str:
        return os.path.basename(self.__codeunit_folder)
    
    @GeneralUtilities.check_arguments
    def get_repository_folder(self)->str:
        return self.__repository_folder
    
    @GeneralUtilities.check_arguments
    def get_product_name(self)->str:
        return self.__read_product_information_property("producttitle")

    @GeneralUtilities.check_arguments
    def get_remote_address(self)->str:
        return self.__read_product_information_property("remoteaddress")

    @GeneralUtilities.check_arguments
    def __read_product_information_property(self, property_name: str) -> str:
        product_information_file = os.path.join(self.get_repository_folder(), ".ScriptCollection", "ProductInformation.xml")
        GeneralUtilities.assert_file_exists(product_information_file)
        root: etree._ElementTree = etree.parse(product_information_file)
        return str(root.xpath(f'/cps:productinformation/cps:{property_name}/text()', namespaces={'cps': 'https://projects.aniondev.de/PublicProjects/Common/ProjectTemplates/-/tree/main/Conventions/RepositoryStructure/CommonProjectStructure'})[0])
    
    @GeneralUtilities.check_arguments
    def get_current_folder(self)->str:
        return self.__current_folder
    
    @GeneralUtilities.check_arguments
    def get_verbosity(self)->LogLevel:
        return self.__verbosity

    @GeneralUtilities.check_arguments
    def get_artifacts_folder(self) -> str:
        return os.path.join(self.get_codeunit_folder(), "Other", "Artifacts")

    @GeneralUtilities.check_arguments
    def get_codeunit_file(self) -> str:
        return os.path.join(self.get_codeunit_folder(), f"{self.get_codeunit_name()}.codeunit.xml")

    def get_type_environment_type(self)->str:
        return self.__target_environment_type

    def get_target_environment_type(self)->str:
        return self.__target_environment_type
    
    @GeneralUtilities.check_arguments
    def copy_source_files_to_output_directory(self) -> None:
        self._protected_sc.log.log("Copy sourcecode...")
        codeunit_folder =self.get_codeunit_folder()
        result = self._protected_sc.run_program_argsasarray("git", ["ls-tree", "-r", "HEAD", "--name-only"], codeunit_folder)
        files = [f for f in result[1].split('\n') if len(f) > 0]
        for file in files:
            full_source_file = os.path.join(codeunit_folder, file)
            if os.path.isfile(full_source_file):
                # Reson of isdir-check:
                # Prevent trying to copy files which are not exist.
                # Otherwise exceptions occurr because uncommitted deletions of files will result in an error here.
                target_file = os.path.join(codeunit_folder, "Other", "Artifacts", "SourceCode", file)
                target_folder = os.path.dirname(target_file)
                GeneralUtilities.ensure_directory_exists(target_folder)
                shutil.copyfile(full_source_file, target_file)

    @GeneralUtilities.check_arguments
    def run_testcases_common_post_task(self, repository_folder: str, codeunit_name: str, generate_badges: bool, targetenvironmenttype: str) -> None:
        self._protected_sc.assert_is_git_repository(repository_folder)
        coverage_file_folder = os.path.join(repository_folder, codeunit_name, "Other/Artifacts/TestCoverage")
        coveragefiletarget = os.path.join(coverage_file_folder,  "TestCoverage.xml")
        self.__update_path_of_source_in_testcoverage_file(repository_folder, codeunit_name)
        self.__standardized_tasks_generate_coverage_report(repository_folder, codeunit_name, generate_badges, targetenvironmenttype)
        self.__check_testcoverage(coveragefiletarget, repository_folder, codeunit_name)
        self.__format_xml_file(coveragefiletarget)

    @GeneralUtilities.check_arguments
    def __format_xml_file(self, xmlfile:str) -> None:
        GeneralUtilities.write_text_to_file(xmlfile,self.__format_xml_content( GeneralUtilities.read_text_from_file(xmlfile)))

    @GeneralUtilities.check_arguments
    def __format_xml_content(self, xml:str) -> None:
        root = etree.fromstring(xml)
        return etree.tostring(root, pretty_print=True, encoding="unicode")

    @GeneralUtilities.check_arguments
    def __standardized_tasks_generate_coverage_report(self, repository_folder: str, codeunitname: str, generate_badges: bool, targetenvironmenttype: str, add_testcoverage_history_entry: bool = None) -> None:
        """This function expects that the file '<repositorybasefolder>/<codeunitname>/Other/Artifacts/TestCoverage/TestCoverage.xml'
        which contains a test-coverage-report in the cobertura-format exists.
        This script expectes that the testcoverage-reportfolder is '<repositorybasefolder>/<codeunitname>/Other/Artifacts/TestCoverageReport'.
        This script expectes that a test-coverage-badges should be added to '<repositorybasefolder>/<codeunitname>/Other/Resources/Badges'."""
        self._protected_sc.log.log("Generate testcoverage report..")
        self._protected_sc.assert_is_git_repository(repository_folder)
        codeunit_version = self.tfcps_Tools_General.get_version_of_codeunit(self.get_codeunit_file()) 
        verbosity=0#TODO use loglevel-value here
        if verbosity == 0:
            verbose_argument_for_reportgenerator = "Off"
        elif verbosity == 1:
            verbose_argument_for_reportgenerator = "Error"
        elif verbosity == 2:
            verbose_argument_for_reportgenerator = "Info"
        elif verbosity == 3:
            verbose_argument_for_reportgenerator = "Verbose"
        else:
            raise ValueError(f"Unknown value for verbosity: {GeneralUtilities.str_none_safe(verbosity)}")

        # Generating report
        GeneralUtilities.ensure_directory_does_not_exist(os.path.join(repository_folder, codeunitname, f"{codeunitname}/Other/Artifacts/TestCoverageReport"))
        GeneralUtilities.ensure_directory_exists(os.path.join(repository_folder, codeunitname, "Other/Artifacts/TestCoverageReport"))

        if add_testcoverage_history_entry is None:
            add_testcoverage_history_entry = self.__is_pre_merge

        history_folder = f"{codeunitname}/Other/Resources/TestCoverageHistory"
        history_folder_full = os.path.join(repository_folder, history_folder)
        GeneralUtilities.ensure_directory_exists(history_folder_full)
        files_before = set(GeneralUtilities.get_direct_files_of_folder(history_folder_full))
        history_argument = f" -historydir:{history_folder}"
        argument = f"-reports:{codeunitname}/Other/Artifacts/TestCoverage/TestCoverage.xml -targetdir:{codeunitname}/Other/Artifacts/TestCoverageReport --verbosity:{verbose_argument_for_reportgenerator}{history_argument} -title:{codeunitname} -tag:v{codeunit_version}"
        self._protected_sc.run_program("reportgenerator", argument, repository_folder)
        if not add_testcoverage_history_entry:
            files_after = set(GeneralUtilities.get_direct_files_of_folder(history_folder_full))
            for new_file in files_after - files_before:
                GeneralUtilities.ensure_file_does_not_exist(new_file)

        # Generating badges
        if generate_badges:
            testcoverageubfolger = "Other/Resources/TestCoverageBadges"
            fulltestcoverageubfolger = os.path.join(repository_folder, codeunitname, testcoverageubfolger)
            GeneralUtilities.ensure_directory_does_not_exist(fulltestcoverageubfolger)
            GeneralUtilities.ensure_directory_exists(fulltestcoverageubfolger)
            self._protected_sc.run_program("reportgenerator", f"-reports:Other/Artifacts/TestCoverage/TestCoverage.xml -targetdir:{testcoverageubfolger} -reporttypes:Badges --verbosity:{verbose_argument_for_reportgenerator}", os.path.join(repository_folder, codeunitname))

    @GeneralUtilities.check_arguments
    def __update_path_of_source_in_testcoverage_file(self, repository_folder: str, codeunitname: str) -> None:
        self._protected_sc.assert_is_git_repository(repository_folder)
        self._protected_sc.log.log("Update paths of source files in testcoverage files..")
        folder = f"{repository_folder}/{codeunitname}/Other/Artifacts/TestCoverage"
        filename = "TestCoverage.xml"
        full_file = os.path.join(folder, filename)
        GeneralUtilities.write_text_to_file(full_file, re.sub("<source>.+<\\/source>", f"<source><!--[repository]/-->./{codeunitname}/</source>", GeneralUtilities.read_text_from_file(full_file)))
        self.__remove_not_existing_files_from_testcoverage_file(full_file, repository_folder, codeunitname)

    @GeneralUtilities.check_arguments
    def __remove_not_existing_files_from_testcoverage_file(self, testcoveragefile: str, repository_folder: str, codeunit_name: str) -> None:
        self._protected_sc.assert_is_git_repository(repository_folder)
        root: etree._ElementTree = etree.parse(testcoveragefile)
        codeunit_folder = os.path.join(repository_folder, codeunit_name)
        xpath = f"//coverage/packages/package[@name='{codeunit_name}']/classes/class"
        coverage_report_classes = root.xpath(xpath)
        found_existing_files = False
        for coverage_report_class in coverage_report_classes:
            filename = coverage_report_class.attrib['filename']
            file = os.path.join(codeunit_folder, filename)
            if os.path.isfile(file):
                found_existing_files = True
            else:
                coverage_report_class.getparent().remove(coverage_report_class)
        GeneralUtilities.assert_condition(found_existing_files, f"No existing files in testcoverage-report-file \"{testcoveragefile}\".")
        result = etree.tostring(root).decode("utf-8")
        GeneralUtilities.write_text_to_file(testcoveragefile, result)

    @GeneralUtilities.check_arguments
    def __check_testcoverage(self, testcoverage_file_in_cobertura_format: str, repository_folder: str, codeunitname: str) -> None:
        self._protected_sc.assert_is_git_repository(repository_folder)
        self._protected_sc.log.log("Check testcoverage..")
        root: etree._ElementTree = etree.parse(testcoverage_file_in_cobertura_format)
        if len(root.xpath('//coverage/packages/package')) != 1:
            raise ValueError(f"'{testcoverage_file_in_cobertura_format}' must contain exactly 1 package.")
        if root.xpath('//coverage/packages/package[1]/@name')[0] != codeunitname:
            raise ValueError(f"The package name of the tested package in '{testcoverage_file_in_cobertura_format}' must be '{codeunitname}'.")
        rates=root.xpath('//coverage/packages/package[1]/@line-rate')
        coverage_in_percent = round(float(str(rates[0]))*100, 2)
        technicalminimalrequiredtestcoverageinpercent = 0
        if not technicalminimalrequiredtestcoverageinpercent < coverage_in_percent:
            raise ValueError(f"The test-coverage of package '{codeunitname}' must be greater than {technicalminimalrequiredtestcoverageinpercent}%.")
        minimalrequiredtestcoverageinpercent = self.get_testcoverage_threshold_from_codeunit_file()
        if (coverage_in_percent < minimalrequiredtestcoverageinpercent):
            raise ValueError(f"The testcoverage for codeunit {codeunitname} must be {minimalrequiredtestcoverageinpercent}% or more but is {coverage_in_percent}%.")

    @GeneralUtilities.check_arguments
    def get_testcoverage_threshold_from_codeunit_file(self):
        root: etree._ElementTree = etree.parse(self.get_codeunit_file())
        return float(str(root.xpath('//cps:properties/cps:testsettings/@minimalcodecoverageinpercent', namespaces={'cps': 'https://projects.aniondev.de/PublicProjects/Common/ProjectTemplates/-/tree/main/Conventions/RepositoryStructure/CommonProjectStructure'})[0]))


    @GeneralUtilities.check_arguments
    def install_requirementstxt_for_codeunit(self):
        self._protected_sc.install_requirementstxt_file(self.get_codeunit_folder()+"/requirements.txt")

class TFCPS_CodeUnitSpecific_Base_CLI():

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_base_parser()->argparse.ArgumentParser:
        parser = argparse.ArgumentParser()
        verbosity_values = ", ".join(f"{lvl.value}={lvl.name}" for lvl in LogLevel)
        parser.add_argument('-e', '--targetenvironmenttype', required=False, default="QualityCheck")
        parser.add_argument('-a', '--additionalargumentsfile', required=False, default=None)
        parser.add_argument('-v', '--verbosity', required=False, default=3, help=f"Sets the loglevel. Possible values: {verbosity_values}")
        parser.add_argument('-c', '--nocache',  action='store_true', required=False, default=False)
        parser.add_argument('-p', '--ispremerge',  action='store_true', required=False, default=False)
        return parser
