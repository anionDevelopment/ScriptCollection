import os
import re
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from lxml import etree
from ...GeneralUtilities import GeneralUtilities
from ...SCLog import  LogLevel
from ..TFCPS_CodeUnitSpecific_Base import TFCPS_CodeUnitSpecific_Base,TFCPS_CodeUnitSpecific_Base_CLI
from ...HTTPMaintenanceOverheadHelper import HTTPMaintenanceOverheadHelper

class TFCPS_CodeUnitSpecific_NodeJS_Functions(TFCPS_CodeUnitSpecific_Base):


    def __init__(self,current_file:str,verbosity:LogLevel,targetenvironmenttype:str,use_cache:bool,is_pre_merge:bool):
        super().__init__(current_file, verbosity,targetenvironmenttype,use_cache,is_pre_merge)


    @GeneralUtilities.check_arguments
    def build(self) -> None:
        self._protected_sc.run_with_epew("npm", "run build", self.get_codeunit_folder(),print_live_output=self.get_verbosity()==LogLevel.Debug,encode_argument_in_base64=True)
        self.standardized_tasks_build_bom_for_node_project()
        self.copy_source_files_to_output_directory()

    @GeneralUtilities.check_arguments
    def linting(self) -> None:
        codeunit_folder = self.get_codeunit_folder()
        self._protected_sc.normalize_line_endings_of_files_in_folder(codeunit_folder, ["ts", "js", "css", "scss", "sass"])
        # The OpenAPI-generator writes its '.openapi-generator/FILES' metadata-file with the host's native
        # line-endings (CRLF on Windows, LF on Linux). Normalize it to LF like the other generated text-files
        # so the committed file does not drift between build-hosts.
        for openapi_generator_files_file in self._protected_sc.get_not_git_ignored_files_of_folder(codeunit_folder):
            if os.path.basename(openapi_generator_files_file) == "FILES" and os.path.basename(os.path.dirname(openapi_generator_files_file)) == ".openapi-generator":
                self._protected_sc.normalize_line_endings(openapi_generator_files_file)
        for html_file in self._protected_sc.get_not_git_ignored_files_of_folder(codeunit_folder, ".html"):
            self._protected_sc.format_html_file(html_file, os.path.basename(html_file) == "index.html")
        self._protected_sc.run_with_epew("npm", "run lint", codeunit_folder,print_live_output=self.get_verbosity()==LogLevel.Debug,encode_argument_in_base64=True)

    @GeneralUtilities.check_arguments
    def do_common_tasks(self,current_codeunit_version:str)-> None:
        codeunit_version = current_codeunit_version
        codeunit_folder = self.get_codeunit_folder()
        self.do_common_tasks_base(current_codeunit_version)
        self.tfcps_Tools_General.replace_version_in_packagejson_file(GeneralUtilities.resolve_relative_path("./package.json", codeunit_folder), codeunit_version)
        self.tfcps_Tools_General.do_npm_install(codeunit_folder, True,self.use_cache())

    @GeneralUtilities.check_arguments
    def generate_reference(self) -> None:
        self.generate_reference_using_docfx()

    
    @GeneralUtilities.check_arguments
    def run_testcases(self) -> None:
        # prepare
        codeunit_name: str =self.get_codeunit_name()
        
        codeunit_folder =self.get_codeunit_folder()
        repository_folder = os.path.dirname(codeunit_folder)

        # run testcases
        self._protected_sc.run_with_epew("npm", f"run test-{self.get_target_environment_type()}", self.get_codeunit_folder(),print_live_output=self.get_verbosity()==LogLevel.Debug,encode_argument_in_base64=True)

        # rename file
        coverage_folder = os.path.join(codeunit_folder, "Other", "Artifacts", "TestCoverage")
        target_file = os.path.join(coverage_folder, "TestCoverage.xml")
        GeneralUtilities.ensure_file_does_not_exist(target_file)
        os.rename(os.path.join(coverage_folder, "cobertura-coverage.xml"), target_file)
        self.__rename_packagename_in_coverage_file(target_file, codeunit_name)

        # adapt backslashs to slashs
        content = GeneralUtilities.read_text_from_file(target_file)
        content = re.sub('\\\\', '/', content)
        GeneralUtilities.write_text_to_file(target_file, content)

        # aggregate packages in testcoverage-file
        roottree: etree._ElementTree = etree.parse(target_file)
        existing_classes = list(roottree.xpath('//coverage/packages/package/classes/class'))

        old_packages_list = roottree.xpath('//coverage/packages/package')
        for package in old_packages_list:
            package.getparent().remove(package)

        root = roottree.getroot()
        packages_element = root.find("packages")
        package_element = etree.SubElement(packages_element, "package")
        package_element.attrib['name'] = codeunit_name
        package_element.attrib['lines-valid'] = root.attrib["lines-valid"]
        package_element.attrib['lines-covered'] = root.attrib["lines-covered"]
        package_element.attrib['line-rate'] = root.attrib["line-rate"]
        package_element.attrib['branches-valid'] = root.attrib["branches-valid"]
        package_element.attrib['branches-covered'] = root.attrib["branches-covered"]
        package_element.attrib['branch-rate'] = root.attrib["branch-rate"]
        package_element.attrib['timestamp'] = root.attrib["timestamp"]
        package_element.attrib['complexity'] = root.attrib["complexity"]

        classes_element = etree.SubElement(package_element, "classes")

        for existing_class in existing_classes:
            classes_element.append(existing_class)

        result = etree.tostring(roottree, pretty_print=True).decode("utf-8")
        GeneralUtilities.write_text_to_file(target_file, result)

        # post tasks
        self.run_testcases_common_post_task(repository_folder, codeunit_name, True, self.get_target_environment_type())

    @GeneralUtilities.check_arguments
    def __rename_packagename_in_coverage_file(self, file: str, codeunit_name: str) -> None:
        root: etree._ElementTree = etree.parse(file)
        packages = root.xpath('//coverage/packages/package')
        for package in packages:
            package.attrib['name'] = codeunit_name
        result = etree.tostring(root).decode("utf-8")
        GeneralUtilities.write_text_to_file(file, result)


    @GeneralUtilities.check_arguments 
    def standardized_tasks_build_bom_for_node_project(self) -> None:
        relative_path_to_bom_file = f"Other/Artifacts/BOM/{os.path.basename(self.get_codeunit_folder())}.{self.tfcps_Tools_General.get_version_of_codeunit(self.get_codeunit_file())}.sbom.xml"
        self._protected_sc.run_with_epew("cyclonedx-npm", f"--output-format xml --output-file {relative_path_to_bom_file}", self.get_codeunit_folder(),print_live_output=self._protected_sc.log.loglevel==LogLevel.Diagnostic,encode_argument_in_base64=True)
        self._protected_sc.format_xml_file(self.get_codeunit_folder()+"/"+relative_path_to_bom_file)

    def get_dependencies(self)->dict[str,set[str]]:
        return dict[str,set[str]]()#TODO
    
    @GeneralUtilities.check_arguments
    def get_available_versions(self,dependencyname:str)->list[str]:
        return []#TODO
    
    @GeneralUtilities.check_arguments
    def set_dependency_version(self,name:str,new_version:str)->None:
        raise ValueError(f"Operation is not implemented.")
    
    @GeneralUtilities.check_arguments
    def add_culture_chooser(self,site_title:str,supported_cultures:list[str])->None:
        output_folder=self.get_codeunit_folder()+"/Other/Artifacts/BuildResult_WebApplication/browser"
        GeneralUtilities.assert_folder_exists(output_folder)
        cc:HTTPMaintenanceOverheadHelper=HTTPMaintenanceOverheadHelper()

        index_html_file=output_folder+"/index.html"
        GeneralUtilities.ensure_file_exists(index_html_file)
        index_html_content=cc.get_index_html(site_title)
        GeneralUtilities.write_text_to_file(index_html_file, index_html_content)

        cc_script_file=output_folder+"/CultureChooser.js"
        GeneralUtilities.ensure_file_exists(cc_script_file)
        cc_script_content=cc.get_culture_chooser_script(supported_cultures)
        GeneralUtilities.write_text_to_file(cc_script_file, cc_script_content)
    
    @GeneralUtilities.check_arguments
    def add_maintenance_site(self,site_title:str)->None:
        output_folder_base=self.get_codeunit_folder()+"/Other/Artifacts/BuildResult_WebApplication"
        GeneralUtilities.assert_folder_exists(output_folder_base)
        output_folder=os.path.join(output_folder_base,"maintenance")
        GeneralUtilities.ensure_directory_exists(output_folder)
        cc:HTTPMaintenanceOverheadHelper=HTTPMaintenanceOverheadHelper()

        maintenance_file=output_folder+"/MaintenanceSite.html"
        GeneralUtilities.ensure_file_exists(maintenance_file)
        maintenance_content=cc.get_maintenance_file(site_title)
        GeneralUtilities.write_text_to_file(maintenance_file, maintenance_content)

    
    @GeneralUtilities.check_arguments
    def get_available_cultures_for_angular_app(self)->None:
        return self._protected_sc.get_available_cultures_for_angular_app(self.get_codeunit_folder()+"/angular.json")

    @GeneralUtilities.check_arguments
    def __ensure_translations_exist(self,languages:list[str])->None:
        base_file=os.path.join(self.get_codeunit_folder(),"Other","Resources","Translations",f"messages.xlf")
        for language in languages:
            target_file=os.path.join(self.get_codeunit_folder(),"Other","Resources","Translations",f"messages.{language}.xlf")
            if not os.path.isfile(target_file):
                GeneralUtilities.ensure_file_exists(target_file)
                GeneralUtilities.write_text_to_file(target_file, GeneralUtilities.read_text_from_file(base_file))
                #set new attribute
                tree = ET.parse(target_file)
                root = tree.getroot()
                ns_prefix = "{urn:oasis:names:tc:xliff:document:2.0}" 
                for unit in root.findall(f".//{ns_prefix}unit"):
                    for segment in unit.findall(f"{ns_prefix}segment"):
                        segment.set("state", "initial")
                tree.write(target_file, encoding="utf-8", xml_declaration=True)

        angular_json_file=self.get_codeunit_folder()+"/angular.json"
        if os.path.isfile(angular_json_file):
            angular_json_path = Path(angular_json_file)
            with angular_json_path.open(encoding="utf-8") as f:
                angular_config = json.load(f)
            i18n_config = angular_config["projects"][self.get_codeunit_name()]["i18n"]
            new_locales = {
                lang: f"Other/Resources/Translations/messages.{lang}.xlf"
                for lang in languages
            }
            i18n_config.setdefault("locales", {}).update(new_locales)
            with angular_json_path.open("w", encoding="utf-8") as f:
                json.dump(angular_config, f, ensure_ascii=False, indent=2)

    @GeneralUtilities.check_arguments
    def organize_translations(self,languages:list[str])->None:
        self._protected_sc.run_with_epew("npm","run extract-translations",self.get_codeunit_folder())
        self.__ensure_translations_exist(languages)
        self._protected_sc.sync_xlf2_files("messages",languages,os.path.join(self.get_codeunit_folder(),"Other","Resources","Translations"))

    @GeneralUtilities.check_arguments
    def translate_safe(self,base_language:str="en", throw_if_no_credentials:bool=False)->None:
        """Translates XLF files if a translation service is configured. The translation service can be configured by creating a file at ~/.ScriptCollection/TranslationServiceProperties.txt with the content 'LibreTranslateAPI=your_api_server_url'."""
        translationservice_file:str=self._protected_sc.get_global_cache_folder()+"/TranslationServiceProperties.txt"
        api_server:str=None
        if os.path.isfile(translationservice_file):
            lines=GeneralUtilities.read_nonempty_lines_from_file(translationservice_file)
            for line in lines:
                if line.startswith("LibreTranslateAPI="):
                    api_server=line.replace("LibreTranslateAPI=","").strip()
        if api_server is None:
            if throw_if_no_credentials:
                raise ValueError("No translation service configured. Please create a file at ~/.ScriptCollection/TranslationServiceProperties.txt with the content 'LibreTranslateAPI=your_api_server_url' to enable automatic translation of XLF files.")
        else:
            self.translate(api_server,base_language)

    @GeneralUtilities.check_arguments
    def translate(self,api_server:str,base_language:str="en")->None:
        folder:str=os.path.join(self.get_codeunit_folder(),"Other","Resources","Translations")
        self._protected_sc.translate_xlf_files_in_folder(folder, base_language, api_server)

class TFCPS_CodeUnitSpecific_NodeJS_CLI:

    @staticmethod
    @GeneralUtilities.check_arguments
    def parse(file:str)->TFCPS_CodeUnitSpecific_NodeJS_Functions:
        parser=TFCPS_CodeUnitSpecific_Base_CLI.get_base_parser()
        #add custom parameter if desired
        args=parser.parse_args()
        result:TFCPS_CodeUnitSpecific_NodeJS_Functions=TFCPS_CodeUnitSpecific_NodeJS_Functions(file,LogLevel(int(args.verbosity)),args.targetenvironmenttype,not args.nocache,args.ispremerge)
        return result
