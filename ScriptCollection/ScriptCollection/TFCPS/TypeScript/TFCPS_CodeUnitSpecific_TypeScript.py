import os
import re
import json
import shutil
import requests
from lxml import etree
from ...GeneralUtilities import GeneralUtilities, Dependency
from ...SCLog import LogLevel
from ..TFCPS_CodeUnitSpecific_Base import TFCPS_CodeUnitSpecific_Base, TFCPS_CodeUnitSpecific_Base_CLI

class TFCPS_CodeUnitSpecific_TypeScript_Functions(TFCPS_CodeUnitSpecific_Base):
    """Implements the tasks of a codeunit which contains a plain typescript-project.

    The typescript-project is expected in "<codeunit>/<codeunit>" and it contains its testcases in the same
    project, because a testcase of a typescript-project belongs next to the file it tests and because the
    compiler has to see the testcases and the sourcecode as one program to be able to check the types of both.

    This implementation exists next to TFCPS_CodeUnitSpecific_NodeJS: the nodejs-implementation delegates
    every task to a script of the package-file, which means every codeunit has to define the same set of
    scripts itself. This implementation calls the tools directly instead, so a codeunit only has to declare
    the dependencies and the configuration of those tools."""

    def __init__(self, current_file: str, verbosity: LogLevel, targetenvironmenttype: str, use_cache: bool, is_pre_merge: bool):
        super().__init__(current_file, verbosity, targetenvironmenttype, use_cache, is_pre_merge)

    @GeneralUtilities.check_arguments
    def get_typescript_project_folder(self) -> str:
        """Returns the folder which contains the package-file of this codeunit."""
        return os.path.join(self.get_codeunit_folder(), self.get_codeunit_name())

    @GeneralUtilities.check_arguments
    def get_package_json_file(self) -> str:
        return os.path.join(self.get_typescript_project_folder(), "package.json")

    @GeneralUtilities.check_arguments
    def build(self) -> None:
        # The sourcecode-artifact of a previous run is removed before the build, because it is a copy of the
        # codeunit inside the codeunit. The compiler would otherwise see the copied sourcecode as part of the
        # program and would report every declaration of it as a duplicate.
        GeneralUtilities.ensure_directory_does_not_exist(os.path.join(self.get_artifacts_folder(), "SourceCode"))
        build_output_folder = os.path.join(self.get_typescript_project_folder(), "dist")
        GeneralUtilities.ensure_directory_does_not_exist(build_output_folder)
        self.__run_npx("tsc --project tsconfig.json")
        GeneralUtilities.assert_condition(os.path.isdir(build_output_folder), f'The compilation did not produce an output in "{build_output_folder}".')
        target_folder = os.path.join(self.get_artifacts_folder(), "BuildResult_TypeScript")
        GeneralUtilities.ensure_directory_does_not_exist(target_folder)
        shutil.copytree(build_output_folder, target_folder)
        self.__generate_bom_for_typescript_project()
        self.copy_source_files_to_output_directory()

    @GeneralUtilities.check_arguments
    def __generate_bom_for_typescript_project(self) -> None:
        codeunit_version = self.tfcps_Tools_General.get_version_of_codeunit(self.get_codeunit_file())
        bom_folder = os.path.join(self.get_artifacts_folder(), "BOM")
        GeneralUtilities.ensure_directory_exists(bom_folder)
        target_bom_file = os.path.join(bom_folder, f"{self.get_codeunit_name()}.{codeunit_version}.bom.xml")
        # The output-file is passed as a path which is relative to the project-folder, because cyclonedx-npm
        # resolves it against its working-directory.
        relative_target_bom_file = os.path.relpath(target_bom_file, self.get_typescript_project_folder()).replace("\\", "/")
        self.__run_npx(f"@cyclonedx/cyclonedx-npm --output-format xml --output-file {relative_target_bom_file}")
        GeneralUtilities.assert_file_exists(target_bom_file)
        self._protected_sc.format_xml_file(target_bom_file)

    @GeneralUtilities.check_arguments
    def linting(self) -> None:
        codeunit_folder = self.get_codeunit_folder()
        self._protected_sc.normalize_invisible_characters_of_files_in_folder(codeunit_folder, ["ts", "js", "json"])
        # "--max-warnings 0" makes a warning fail the linting as well, because a warning is a linting-issue too.
        self.__run_npx("eslint . --max-warnings 0")

    @GeneralUtilities.check_arguments
    def do_common_tasks(self, current_codeunit_version: str) -> None:
        self.do_common_tasks_base(current_codeunit_version)
        self.tfcps_Tools_General.replace_version_in_packagejson_file(self.get_package_json_file(), current_codeunit_version)
        self.tfcps_Tools_General.do_npm_install(self.get_typescript_project_folder(), True, self.use_cache())

    @GeneralUtilities.check_arguments
    def generate_reference(self) -> None:
        # docfx can not extract a class-reference from typescript-sourcecode, so only the articles of the
        # reference-content are generated.
        self.generate_reference_using_docfx()

    @GeneralUtilities.check_arguments
    def run_testcases(self) -> None:
        codeunit_name = self.get_codeunit_name()
        coverage_folder = os.path.join(self.get_artifacts_folder(), "TestCoverage")
        GeneralUtilities.ensure_directory_exists(coverage_folder)
        coverage_file = os.path.join(coverage_folder, "TestCoverage.xml")
        GeneralUtilities.ensure_file_does_not_exist(coverage_file)
        generated_coverage_file = os.path.join(self.get_typescript_project_folder(), "coverage", "cobertura-coverage.xml")
        GeneralUtilities.ensure_file_does_not_exist(generated_coverage_file)
        self.__run_npx("jest --coverage --coverageReporters=cobertura")
        GeneralUtilities.assert_file_exists(generated_coverage_file)
        shutil.move(generated_coverage_file, coverage_file)
        self.__normalize_coverage_file(coverage_file)
        self.run_testcases_common_post_task(self.get_repository_folder(), codeunit_name, True, self.get_target_environment_type())

    @GeneralUtilities.check_arguments
    def __normalize_coverage_file(self, coverage_file: str) -> None:
        """Makes the coverage-report which jest wrote match the expectations of the further processing: it must
        contain exactly one package which is named like the codeunit, and the filename of a class must be
        relative to the codeunit-folder, while jest writes it relative to the project-folder."""
        codeunit_name = self.get_codeunit_name()
        tree = etree.parse(coverage_file)
        root = tree.getroot()
        for package in root.findall(".//package"):
            package.set("name", codeunit_name)
        for class_element in root.findall(".//class"):
            filename = class_element.get("filename")
            if filename is not None:
                filename_with_slashes = filename.replace("\\", "/")
                class_element.set("filename", f"{codeunit_name}/{filename_with_slashes}")
                class_element.set("name", os.path.basename(filename_with_slashes))
        tree.write(coverage_file, pretty_print=True, xml_declaration=True, encoding="UTF-8")
        self.tfcps_Tools_General.merge_packages(coverage_file, codeunit_name)

    @GeneralUtilities.check_arguments
    def __run_npx(self, arguments: str) -> None:
        # The tools are run through npx instead of through a script of the package-file, so that a codeunit does
        # not have to define a script for every task. "--no-install" makes npx fail instead of downloading a tool
        # which the package-file does not declare, because a build must not depend on what npx finds online.
        self._protected_sc.run_with_epew("npx", f"--no-install {arguments}", self.get_typescript_project_folder(), print_live_output=self.get_verbosity() == LogLevel.Debug, encode_argument_in_base64=True)

    @GeneralUtilities.check_arguments
    def get_dependencies(self) -> dict[str, set[str]]:
        return GeneralUtilities.merge_dependency_lists([self.__get_dependencies_from_package_json_file()])

    @GeneralUtilities.check_arguments
    def __get_dependencies_from_package_json_file(self) -> list[Dependency]:
        result: list[Dependency] = []
        for name, dependency_version in self.__enumerate_dependency_entries():
            result.append(Dependency(name, dependency_version))
        return result

    @GeneralUtilities.check_arguments
    def __enumerate_dependency_entries(self) -> list[tuple[str, str]]:
        """Returns the dependencies of the package-file as tuples of their name and their version. Only a
        dependency whose version is a plain version-number is returned, because a dependency which points to a
        file, a repository or a tag has no version which could be updated."""
        content = json.loads(GeneralUtilities.read_text_from_file(self.get_package_json_file()))
        result: list[tuple[str, str]] = []
        for section in ("dependencies", "devDependencies"):
            for name, declared_version in content.get(section, {}).items():
                # A declared version usually carries a range-prefix ("^1.2.3" or "~1.2.3"), which is not part of
                # the version itself.
                version_without_prefix = declared_version.lstrip("^~")
                if re.match(r"^\d+\.\d+\.\d+$", version_without_prefix) is not None:
                    result.append((name, version_without_prefix))
        return result

    @GeneralUtilities.check_arguments
    def get_available_versions(self, dependencyname: str) -> list[str]:
        # The registry of npm answers with all published versions of a package.
        response = requests.get(f"https://registry.npmjs.org/{dependencyname}", headers={"Accept": "application/vnd.npm.install-v1+json"}, timeout=60)
        response.raise_for_status()
        result: list[str] = []
        for version_string in response.json().get("versions", {}).keys():
            if re.match(r"^\d+\.\d+\.\d+$", version_string) is not None:
                result.append(version_string)
        return result

    @GeneralUtilities.check_arguments
    def set_dependency_version(self, name: str, new_version: str) -> None:
        package_json_file = self.get_package_json_file()
        content = json.loads(GeneralUtilities.read_text_from_file(package_json_file))
        dependency_was_set: bool = False
        for section in ("dependencies", "devDependencies"):
            if name in content.get(section, {}):
                # The range-prefix of the former declaration is kept, because it states how the project wants to
                # accept updates and that is not a decision of this function.
                former_declaration = content[section][name]
                prefix = former_declaration[0] if former_declaration[0] in ("^", "~") else GeneralUtilities.empty_string
                content[section][name] = f"{prefix}{new_version}"
                dependency_was_set = True
        GeneralUtilities.assert_condition(dependency_was_set, f'The package-file "{package_json_file}" does not contain a dependency which is named "{name}".')
        GeneralUtilities.write_text_to_file(package_json_file, json.dumps(content, indent=2, ensure_ascii=False) + "\n")
        self._protected_sc.format_json_file(package_json_file)

class TFCPS_CodeUnitSpecific_TypeScript_CLI:

    @staticmethod
    @GeneralUtilities.check_arguments
    def parse(file: str) -> TFCPS_CodeUnitSpecific_TypeScript_Functions:
        parser = TFCPS_CodeUnitSpecific_Base_CLI.get_base_parser()
        #add custom parameter if desired
        args = parser.parse_args()
        result: TFCPS_CodeUnitSpecific_TypeScript_Functions = TFCPS_CodeUnitSpecific_TypeScript_Functions(file, LogLevel(int(args.verbosity)), args.targetenvironmenttype, not args.nocache, args.ispremerge)
        return result
