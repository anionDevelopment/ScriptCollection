import os
import re
import shutil
import requests
from lxml import etree
from ...GeneralUtilities import GeneralUtilities, Dependency
from ...SCLog import LogLevel
from ..TFCPS_CodeUnitSpecific_Base import TFCPS_CodeUnitSpecific_Base, TFCPS_CodeUnitSpecific_Base_CLI

class TFCPS_CodeUnitSpecific_Rust_Functions(TFCPS_CodeUnitSpecific_Base):
    """Implements the tasks of a codeunit which contains a cargo-project.

    The cargo-project is expected in "<codeunit>/<codeunit>" and it contains its testcases in the same
    project, because that is the layout cargo defines: unit-tests live next to the code they test and
    integration-tests live in the "tests"-folder of the project."""

    def __init__(self, current_file: str, verbosity: LogLevel, targetenvironmenttype: str, use_cache: bool, is_pre_merge: bool):
        super().__init__(current_file, verbosity, targetenvironmenttype, use_cache, is_pre_merge)

    @GeneralUtilities.check_arguments
    def get_cargo_project_folder(self) -> str:
        """Returns the folder which contains the Cargo.toml-file of this codeunit."""
        return os.path.join(self.get_codeunit_folder(), self.get_codeunit_name())

    @GeneralUtilities.check_arguments
    def get_cargo_file(self) -> str:
        return os.path.join(self.get_cargo_project_folder(), "Cargo.toml")

    @GeneralUtilities.check_arguments
    def build(self) -> None:
        target_folder = os.path.join(self.get_artifacts_folder(), "BuildResult_Rust")
        GeneralUtilities.ensure_directory_exists(target_folder)
        self.__run_cargo("build --release")
        # cargo puts the executable and the library of the release-profile directly into "target/release"; everything
        # below that folder is intermediate build-output and is therefore not part of the artifact.
        build_output_folder = os.path.join(self.get_cargo_project_folder(), "target", "release")
        artifacts = [file for file in GeneralUtilities.get_direct_files_of_folder(build_output_folder) if TFCPS_CodeUnitSpecific_Rust_Functions.__file_is_build_artifact(file)]
        GeneralUtilities.assert_condition(0 < len(artifacts), f'The cargo-build did not produce an artifact in "{build_output_folder}".')
        for artifact in artifacts:
            shutil.copyfile(artifact, os.path.join(target_folder, os.path.basename(artifact)))
        self.__generate_bom_for_cargo_project()
        self.copy_source_files_to_output_directory()

    @staticmethod
    @GeneralUtilities.check_arguments
    def __file_is_build_artifact(file: str) -> bool:
        # cargo writes further files (for example ".d"-dependency-files and the "*.pdb"-symbols on windows) next to the
        # executable and the library, so the artifact is selected by its extension instead of taking everything.
        extensions_of_artifacts = ("", ".exe", ".dll", ".so", ".dylib", ".a", ".lib", ".rlib")
        return os.path.splitext(file)[1] in extensions_of_artifacts

    @GeneralUtilities.check_arguments
    def __generate_bom_for_cargo_project(self) -> None:
        codeunit_version = self.tfcps_Tools_General.get_version_of_codeunit(self.get_codeunit_file())
        bom_folder = os.path.join(self.get_artifacts_folder(), "BOM")
        GeneralUtilities.ensure_directory_exists(bom_folder)
        target_bom_file = os.path.join(bom_folder, f"{self.get_codeunit_name()}.{codeunit_version}.bom.xml")
        self.__run_cargo("cyclonedx --format xml")
        # cargo-cyclonedx writes its result into the folder of the cargo-project and derives the filename from the name
        # of the crate, so the generated file is searched instead of being predicted from the name of the codeunit.
        generated_bom_files = [file for file in GeneralUtilities.get_direct_files_of_folder(self.get_cargo_project_folder()) if file.endswith(".xml")]
        GeneralUtilities.assert_condition(len(generated_bom_files) == 1, f'Expected exactly one generated bill-of-materials in "{self.get_cargo_project_folder()}" but found {len(generated_bom_files)}.')
        shutil.move(generated_bom_files[0], target_bom_file)
        self._protected_sc.format_xml_file(target_bom_file)

    @GeneralUtilities.check_arguments
    def linting(self) -> None:
        # "--all-targets" includes the testcases in the check, and "-D warnings" makes clippy exit with a non-zero
        # exit-code for a warning as well, because a warning is a linting-issue too.
        self.__run_cargo("clippy --all-targets --all-features -- -D warnings")

    @GeneralUtilities.check_arguments
    def do_common_tasks(self, current_codeunit_version: str) -> None:
        self.do_common_tasks_base(current_codeunit_version)
        self.__set_version_in_cargo_file(self.get_version_of_project())

    @GeneralUtilities.check_arguments
    def generate_reference(self) -> None:
        self.generate_reference_using_docfx()

    @GeneralUtilities.check_arguments
    def run_testcases(self) -> None:
        codeunit_name = self.get_codeunit_name()
        coverage_file = os.path.join(self.get_artifacts_folder(), "TestCoverage", "TestCoverage.xml")
        GeneralUtilities.ensure_directory_exists(os.path.dirname(coverage_file))
        GeneralUtilities.ensure_file_does_not_exist(coverage_file)
        # cargo-llvm-cov runs the testcases and writes the coverage-report in the cobertura-format directly, so no
        # conversion of the report-format is required here.
        self.__run_cargo(f"llvm-cov --all-features --cobertura --output-path {coverage_file}")
        GeneralUtilities.assert_file_exists(coverage_file)
        self.__normalize_coverage_file(coverage_file)
        self.run_testcases_common_post_task(self.get_repository_folder(), codeunit_name, True, self.get_target_environment_type())

    @GeneralUtilities.check_arguments
    def __normalize_coverage_file(self, coverage_file: str) -> None:
        """Makes the coverage-report which cargo-llvm-cov wrote match the expectations of the further processing:
        it must contain exactly one package which is named like the codeunit, and the filename of a class must be
        relative to the codeunit-folder (cargo-llvm-cov writes it relative to the cargo-project-folder)."""
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
    def __run_cargo(self, arguments: str) -> None:
        self._protected_sc.run_program("cargo", arguments, self.get_cargo_project_folder(), print_live_output=self.get_verbosity() == LogLevel.Debug)

    @GeneralUtilities.check_arguments
    def get_dependencies(self) -> dict[str, set[str]]:
        return GeneralUtilities.merge_dependency_lists([self.__get_dependencies_from_cargo_file()])

    @GeneralUtilities.check_arguments
    def __get_dependencies_from_cargo_file(self) -> list[Dependency]:
        result: list[Dependency] = []
        for section, name, dependency_version in self.__enumerate_dependency_entries():
            GeneralUtilities.assert_condition(GeneralUtilities.string_has_content(section), "Internal error while reading the dependencies.")
            result.append(Dependency(name, dependency_version))
        return result

    @GeneralUtilities.check_arguments
    def __enumerate_dependency_entries(self) -> list[tuple[str, str, str]]:
        """Returns the dependencies of the cargo-file as tuples of the section they are declared in, their name and
        their version. Only a dependency which declares a plain version-string is returned, because a dependency which
        is declared as a table (for example a path- or git-dependency) has no version which could be updated."""
        dependency_sections = ("dependencies", "dev-dependencies", "build-dependencies")
        current_section: str = None
        result: list[tuple[str, str, str]] = []
        for line in GeneralUtilities.read_lines_from_file(self.get_cargo_file()):
            stripped_line = line.strip()
            if stripped_line.startswith("[") and stripped_line.endswith("]"):
                current_section = stripped_line[1:-1].strip()
                continue
            if current_section not in dependency_sections or not GeneralUtilities.string_has_content(stripped_line) or stripped_line.startswith("#"):
                continue
            match = re.match(r'^([A-Za-z0-9_\-]+)\s*=\s*"([^"]+)"$', stripped_line)
            if match is not None:
                result.append((current_section, match.group(1), match.group(2)))
        return result

    @GeneralUtilities.check_arguments
    def get_available_versions(self, dependencyname: str) -> list[str]:
        # The crates.io-api answers with all published versions of a crate.
        response = requests.get(f"https://crates.io/api/v1/crates/{dependencyname}/versions", headers={"User-Agent": "ScriptCollection"}, timeout=60)
        response.raise_for_status()
        result: list[str] = []
        for found_version in response.json()["versions"]:
            if found_version.get("yanked", False):
                continue
            version_string = str(found_version["num"])
            if re.match(r"^(\d+)\.(\d+)\.(\d+)$", version_string) is not None:
                result.append(version_string)
        return result

    @GeneralUtilities.check_arguments
    def set_dependency_version(self, name: str, new_version: str) -> None:
        cargo_file = self.get_cargo_file()
        new_lines: list[str] = []
        for line in GeneralUtilities.read_lines_from_file(cargo_file):
            match = re.match(r'^(\s*)('+re.escape(name)+r')(\s*=\s*)"([^"]+)"(\s*)$', line)
            if match is None:
                new_lines.append(line)
            else:
                new_lines.append(f'{match.group(1)}{match.group(2)}{match.group(3)}"{new_version}"')
        GeneralUtilities.write_lines_to_file(cargo_file, new_lines)

    @GeneralUtilities.check_arguments
    def __set_version_in_cargo_file(self, new_version: str) -> None:
        cargo_file = self.get_cargo_file()
        new_lines: list[str] = []
        is_in_package_section: bool = False
        version_was_set: bool = False
        for line in GeneralUtilities.read_lines_from_file(cargo_file):
            stripped_line = line.strip()
            if stripped_line.startswith("[") and stripped_line.endswith("]"):
                is_in_package_section = stripped_line[1:-1].strip() == "package"
            # Only the version in the package-section is the version of the project itself; a version in a
            # dependency-section belongs to a dependency and must not be changed here.
            if is_in_package_section and re.match(r'^version\s*=\s*"[^"]+"$', stripped_line) is not None:
                new_lines.append(f'version = "{new_version}"')
                version_was_set = True
            else:
                new_lines.append(line)
        GeneralUtilities.assert_condition(version_was_set, f'The cargo-file "{cargo_file}" does not contain a version in its package-section.')
        GeneralUtilities.write_lines_to_file(cargo_file, new_lines)

class TFCPS_CodeUnitSpecific_Rust_CLI:

    @staticmethod
    @GeneralUtilities.check_arguments
    def parse(file: str) -> TFCPS_CodeUnitSpecific_Rust_Functions:
        parser = TFCPS_CodeUnitSpecific_Base_CLI.get_base_parser()
        #add custom parameter if desired
        args = parser.parse_args()
        result: TFCPS_CodeUnitSpecific_Rust_Functions = TFCPS_CodeUnitSpecific_Rust_Functions(file, LogLevel(int(args.verbosity)), args.targetenvironmenttype, not args.nocache, args.ispremerge)
        return result
