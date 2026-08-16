import os
import re
import shutil
import requests
from lxml import etree
from ...GeneralUtilities import GeneralUtilities, Dependency
from ...SCLog import LogLevel
from ..TFCPS_CodeUnitSpecific_Base import TFCPS_CodeUnitSpecific_Base, TFCPS_CodeUnitSpecific_Base_CLI

class TFCPS_CodeUnitSpecific_Maven_Functions(TFCPS_CodeUnitSpecific_Base):
    """Implements the tasks of a codeunit which contains a maven-project.

    The maven-project is expected in "<codeunit>/<codeunit>" and it contains its testcases in its own
    "src/test"-folder, because that is the layout maven defines and the layout jacoco measures the
    coverage of without further configuration."""

    __pom_namespace: str = "http://maven.apache.org/POM/4.0.0"

    def __init__(self, current_file: str, verbosity: LogLevel, targetenvironmenttype: str, use_cache: bool, is_pre_merge: bool):
        super().__init__(current_file, verbosity, targetenvironmenttype, use_cache, is_pre_merge)

    @GeneralUtilities.check_arguments
    def get_maven_project_folder(self) -> str:
        """Returns the folder which contains the pom-file of this codeunit."""
        return os.path.join(self.get_codeunit_folder(), self.get_codeunit_name())

    @GeneralUtilities.check_arguments
    def get_pom_file(self) -> str:
        return os.path.join(self.get_maven_project_folder(), "pom.xml")

    @GeneralUtilities.check_arguments
    def build(self) -> None:
        maven_project_folder = self.get_maven_project_folder()
        target_folder = os.path.join(self.get_artifacts_folder(), "BuildResult_Maven")
        GeneralUtilities.ensure_directory_exists(target_folder)
        # The testcases are executed by RunTestcases.py and not by the build, so that a failing testcase is reported
        # by the quality-check and not by the build-step.
        self.__run_maven("-B -DskipTests clean package")
        build_output_folder = os.path.join(maven_project_folder, "target")
        artifacts = [file for file in GeneralUtilities.get_direct_files_of_folder(build_output_folder) if file.endswith(".jar")]
        GeneralUtilities.assert_condition(0 < len(artifacts), f'The maven-build did not produce a jar-file in "{build_output_folder}".')
        for artifact in artifacts:
            shutil.copyfile(artifact, os.path.join(target_folder, os.path.basename(artifact)))
        self.__generate_bom_for_maven_project()
        self.copy_source_files_to_output_directory()

    @GeneralUtilities.check_arguments
    def __generate_bom_for_maven_project(self) -> None:
        codeunit_version = self.tfcps_Tools_General.get_version_of_codeunit(self.get_codeunit_file())
        bom_folder = os.path.join(self.get_artifacts_folder(), "BOM")
        GeneralUtilities.ensure_directory_exists(bom_folder)
        self.__run_maven("-B org.cyclonedx:cyclonedx-maven-plugin:makeAggregateBom")
        generated_bom_file = os.path.join(self.get_maven_project_folder(), "target", "bom.xml")
        GeneralUtilities.assert_file_exists(generated_bom_file)
        target_bom_file = os.path.join(bom_folder, f"{self.get_codeunit_name()}.{codeunit_version}.bom.xml")
        shutil.copyfile(generated_bom_file, target_bom_file)
        self._protected_sc.format_xml_file(target_bom_file)

    @GeneralUtilities.check_arguments
    def linting(self) -> None:
        # checkstyle is configured in the pom-file of the codeunit, so that the ruleset belongs to the codeunit
        # and not to this implementation.
        self.__run_maven("-B checkstyle:check")

    @GeneralUtilities.check_arguments
    def do_common_tasks(self, current_codeunit_version: str) -> None:
        self.do_common_tasks_base(current_codeunit_version)
        self.__set_version_in_pom_file(self.get_version_of_project())

    @GeneralUtilities.check_arguments
    def generate_reference(self) -> None:
        self.generate_reference_using_docfx()

    @GeneralUtilities.check_arguments
    def run_testcases(self) -> None:
        codeunit_name = self.get_codeunit_name()
        # "verify" is used instead of "test" because the report of jacoco is bound to that phase.
        self.__run_maven("-B verify")
        jacoco_file = os.path.join(self.get_maven_project_folder(), "target", "site", "jacoco", "jacoco.xml")
        coverage_file = os.path.join(self.get_artifacts_folder(), "TestCoverage", "TestCoverage.xml")
        GeneralUtilities.ensure_file_does_not_exist(coverage_file)
        self.tfcps_Tools_General.convert_jacoco_report_to_cobertura_report(jacoco_file, coverage_file, codeunit_name, self.get_codeunit_folder(), [f"{codeunit_name}/src/main/java", f"{codeunit_name}/src/test/java"])
        self.run_testcases_common_post_task(self.get_repository_folder(), codeunit_name, True, self.get_target_environment_type())

    @GeneralUtilities.check_arguments
    def __run_maven(self, arguments: str) -> None:
        self._protected_sc.run_program("mvn", arguments, self.get_maven_project_folder(), print_live_output=self.get_verbosity() == LogLevel.Debug)

    @GeneralUtilities.check_arguments
    def get_dependencies(self) -> dict[str, set[str]]:
        return GeneralUtilities.merge_dependency_lists([self.__get_dependencies_from_pom_file()])

    @GeneralUtilities.check_arguments
    def __get_dependencies_from_pom_file(self) -> list[Dependency]:
        root: etree._ElementTree = etree.parse(self.get_pom_file())
        namespaces = {"pom": TFCPS_CodeUnitSpecific_Maven_Functions.__pom_namespace}
        result: list[Dependency] = []
        for dependency in root.xpath("//pom:dependencies/pom:dependency", namespaces=namespaces):
            group_id = dependency.xpath("./pom:groupId/text()", namespaces=namespaces)
            artifact_id = dependency.xpath("./pom:artifactId/text()", namespaces=namespaces)
            dependency_version = dependency.xpath("./pom:version/text()", namespaces=namespaces)
            if len(group_id) == 0 or len(artifact_id) == 0:
                continue
            if len(dependency_version) == 0:
                # The version of such a dependency comes from a parent-pom or from a dependency-management-section,
                # so it can not be updated here.
                continue
            result.append(Dependency(f"{group_id[0]}:{artifact_id[0]}", str(dependency_version[0])))
        return result

    @GeneralUtilities.check_arguments
    def get_available_versions(self, dependencyname: str) -> list[str]:
        group_id, artifact_id = TFCPS_CodeUnitSpecific_Maven_Functions.__split_dependency_name(dependencyname)
        # The maven-central-search-api answers with the released versions of an artifact, newest first.
        response = requests.get("https://search.maven.org/solrsearch/select", params={"q": f'g:"{group_id}" AND a:"{artifact_id}"', "core": "gav", "rows": "200", "wt": "json"}, timeout=60)
        response.raise_for_status()
        result: list[str] = []
        for found_artifact in response.json()["response"]["docs"]:
            found_version = str(found_artifact["v"])
            if re.match(r"^(\d+)\.(\d+)\.(\d+)$", found_version) is not None:
                result.append(found_version)
            elif re.match(r"^(\d+)\.(\d+)$", found_version) is not None:
                result.append(found_version+".0")
            elif re.match(r"^(\d+)$", found_version) is not None:
                result.append(found_version+".0.0")
        return result

    @GeneralUtilities.check_arguments
    def set_dependency_version(self, name: str, new_version: str) -> None:
        group_id, artifact_id = TFCPS_CodeUnitSpecific_Maven_Functions.__split_dependency_name(name)
        pom_file = self.get_pom_file()
        root: etree._ElementTree = etree.parse(pom_file)
        namespaces = {"pom": TFCPS_CodeUnitSpecific_Maven_Functions.__pom_namespace}
        for dependency in root.xpath("//pom:dependencies/pom:dependency", namespaces=namespaces):
            group_id_of_dependency = dependency.xpath("./pom:groupId/text()", namespaces=namespaces)
            artifact_id_of_dependency = dependency.xpath("./pom:artifactId/text()", namespaces=namespaces)
            version_element = dependency.xpath("./pom:version", namespaces=namespaces)
            if len(group_id_of_dependency) == 0 or len(artifact_id_of_dependency) == 0 or len(version_element) == 0:
                continue
            if str(group_id_of_dependency[0]) == group_id and str(artifact_id_of_dependency[0]) == artifact_id:
                version_element[0].text = new_version
        root.write(pom_file, pretty_print=True, xml_declaration=True, encoding="UTF-8")

    @GeneralUtilities.check_arguments
    def __set_version_in_pom_file(self, new_version: str) -> None:
        pom_file = self.get_pom_file()
        root: etree._ElementTree = etree.parse(pom_file)
        namespaces = {"pom": TFCPS_CodeUnitSpecific_Maven_Functions.__pom_namespace}
        # Only the version of the project itself is set here. A version-element inside a dependency is not touched,
        # which is why the version-element is taken from the project-element directly and not searched anywhere.
        version_elements = root.xpath("/pom:project/pom:version", namespaces=namespaces)
        GeneralUtilities.assert_condition(len(version_elements) == 1, f'The pom-file "{pom_file}" must contain exactly one version-element directly in its project-element.')
        version_elements[0].text = new_version
        root.write(pom_file, pretty_print=True, xml_declaration=True, encoding="UTF-8")

    @staticmethod
    @GeneralUtilities.check_arguments
    def __split_dependency_name(dependencyname: str) -> tuple[str, str]:
        """A maven-dependency is identified by its group-id and its artifact-id, so both of them together are used as
        dependency-name in the format "<group-id>:<artifact-id>"."""
        parts = dependencyname.split(":")
        GeneralUtilities.assert_condition(len(parts) == 2, f'The name of a maven-dependency must have the format "<group-id>:<artifact-id>" but was "{dependencyname}".')
        return (parts[0], parts[1])

class TFCPS_CodeUnitSpecific_Maven_CLI:

    @staticmethod
    @GeneralUtilities.check_arguments
    def parse(file: str) -> TFCPS_CodeUnitSpecific_Maven_Functions:
        parser = TFCPS_CodeUnitSpecific_Base_CLI.get_base_parser()
        #add custom parameter if desired
        args = parser.parse_args()
        result: TFCPS_CodeUnitSpecific_Maven_Functions = TFCPS_CodeUnitSpecific_Maven_Functions(file, LogLevel(int(args.verbosity)), args.targetenvironmenttype, not args.nocache, args.ispremerge)
        return result
