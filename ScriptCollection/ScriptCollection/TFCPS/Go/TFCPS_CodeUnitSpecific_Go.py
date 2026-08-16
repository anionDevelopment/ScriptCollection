import os
import re
import requests
from ...GeneralUtilities import GeneralUtilities, Dependency
from ...SCLog import LogLevel
from ..TFCPS_CodeUnitSpecific_Base import TFCPS_CodeUnitSpecific_Base, TFCPS_CodeUnitSpecific_Base_CLI

class TFCPS_CodeUnitSpecific_Go_Functions(TFCPS_CodeUnitSpecific_Base):
    """Implements the tasks of a codeunit which contains a go-module.

    The go-module is expected in "<codeunit>/<codeunit>" and it contains its testcases in the same module,
    because that is the layout go defines: the testcases of a file live in a "_test.go"-file next to it."""

    def __init__(self, current_file: str, verbosity: LogLevel, targetenvironmenttype: str, use_cache: bool, is_pre_merge: bool):
        super().__init__(current_file, verbosity, targetenvironmenttype, use_cache, is_pre_merge)

    @GeneralUtilities.check_arguments
    def get_go_module_folder(self) -> str:
        """Returns the folder which contains the go.mod-file of this codeunit."""
        return os.path.join(self.get_codeunit_folder(), self.get_codeunit_name())

    @GeneralUtilities.check_arguments
    def get_go_module_file(self) -> str:
        return os.path.join(self.get_go_module_folder(), "go.mod")

    @GeneralUtilities.check_arguments
    def get_go_module_name(self) -> str:
        """Returns the name of the go-module as it is declared in the go.mod-file. The paths in the
        coverage-report of go are prefixed with it, so it is required to resolve them."""
        for line in GeneralUtilities.read_lines_from_file(self.get_go_module_file()):
            match = re.match(r"^module\s+(\S+)$", line.strip())
            if match is not None:
                return match.group(1)
        raise ValueError(f'The go-module-file "{self.get_go_module_file()}" does not declare a module-name.')

    @GeneralUtilities.check_arguments
    def build(self) -> None:
        codeunit_name = self.get_codeunit_name()
        target_folder = os.path.join(self.get_artifacts_folder(), "BuildResult_Go")
        GeneralUtilities.ensure_directory_exists(target_folder)
        executable_name = codeunit_name+(".exe" if GeneralUtilities.current_system_is_windows() else GeneralUtilities.empty_string)
        # The package of the module-root is built explicitly ("."). "./..." would build every package of the module,
        # which go refuses when a single output-file is given.
        self.__run_go(f"build -o {os.path.join(target_folder, executable_name)} .")
        self.__generate_bom_for_go_module()
        self.copy_source_files_to_output_directory()

    @GeneralUtilities.check_arguments
    def __generate_bom_for_go_module(self) -> None:
        codeunit_version = self.tfcps_Tools_General.get_version_of_codeunit(self.get_codeunit_file())
        bom_folder = os.path.join(self.get_artifacts_folder(), "BOM")
        GeneralUtilities.ensure_directory_exists(bom_folder)
        target_bom_file = os.path.join(bom_folder, f"{self.get_codeunit_name()}.{codeunit_version}.bom.xml")
        self._protected_sc.run_program("cyclonedx-gomod", f"mod -licenses -output {target_bom_file} -output-version 1.5", self.get_go_module_folder(), print_live_output=self.get_verbosity() == LogLevel.Debug)
        GeneralUtilities.assert_file_exists(target_bom_file)
        self._protected_sc.format_xml_file(target_bom_file)

    @GeneralUtilities.check_arguments
    def linting(self) -> None:
        self.__run_go("vet ./...")
        # "gofmt -l" prints the files which are not formatted as gofmt would format them and exits with 0 either way,
        # so the output has to be evaluated to recognize that there are linting-issues.
        formatting_result = self._protected_sc.run_program("gofmt", "-l .", self.get_go_module_folder())
        unformatted_files = [line.strip() for line in GeneralUtilities.string_to_lines(formatting_result[1]) if GeneralUtilities.string_has_content(line.strip())]
        if 0 < len(unformatted_files):
            for unformatted_file in unformatted_files:
                self._protected_sc.log.log(f'File "{unformatted_file}" is not formatted as gofmt formats it.', LogLevel.Warning)
            raise ValueError(f"{len(unformatted_files)} file(s) are not formatted as gofmt formats them.")

    @GeneralUtilities.check_arguments
    def do_common_tasks(self, current_codeunit_version: str) -> None:
        self.do_common_tasks_base(current_codeunit_version)
        # A go-module does not declare its own version: the version of a go-module is the git-tag it is published with,
        # so there is no version in the go.mod-file which could be set here.

    @GeneralUtilities.check_arguments
    def generate_reference(self) -> None:
        self.generate_reference_using_docfx()

    @GeneralUtilities.check_arguments
    def run_testcases(self) -> None:
        codeunit_name = self.get_codeunit_name()
        go_module_folder = self.get_go_module_folder()
        coverprofile_file = os.path.join(GeneralUtilities.get_temp_folder(), f"{codeunit_name}.coverprofile")
        GeneralUtilities.ensure_file_does_not_exist(coverprofile_file)
        coverage_file = os.path.join(self.get_artifacts_folder(), "TestCoverage", "TestCoverage.xml")
        GeneralUtilities.ensure_file_does_not_exist(coverage_file)
        try:
            # The coverprofile is written into the temp-folder and not into the module-folder, so that a file which is
            # not git-ignored is not left behind in the codeunit when the testcases fail.
            self.__run_go(f"test -coverprofile={coverprofile_file} ./...")
            self.tfcps_Tools_General.convert_go_coverprofile_to_cobertura_report(coverprofile_file, coverage_file, codeunit_name, self.get_codeunit_folder(), self.get_go_module_name(), codeunit_name)
        finally:
            GeneralUtilities.ensure_file_does_not_exist(coverprofile_file)
        self.run_testcases_common_post_task(self.get_repository_folder(), codeunit_name, True, self.get_target_environment_type())

    @GeneralUtilities.check_arguments
    def __run_go(self, arguments: str) -> None:
        self._protected_sc.run_program("go", arguments, self.get_go_module_folder(), print_live_output=self.get_verbosity() == LogLevel.Debug)

    @GeneralUtilities.check_arguments
    def get_dependencies(self) -> dict[str, set[str]]:
        return GeneralUtilities.merge_dependency_lists([self.__get_dependencies_from_go_module_file()])

    @GeneralUtilities.check_arguments
    def __get_dependencies_from_go_module_file(self) -> list[Dependency]:
        result: list[Dependency] = []
        is_in_require_block: bool = False
        for line in GeneralUtilities.read_lines_from_file(self.get_go_module_file()):
            stripped_line = line.strip()
            if stripped_line == "require (":
                is_in_require_block = True
                continue
            if is_in_require_block and stripped_line == ")":
                is_in_require_block = False
                continue
            if stripped_line.startswith("//") or not GeneralUtilities.string_has_content(stripped_line):
                continue
            # A dependency is declared either in a require-block or in a single require-line.
            match = re.match(r"^(?:require\s+)?(\S+)\s+v(\d+\.\d+\.\d+)(?:\s+//.*)?$", stripped_line)
            if match is not None and (is_in_require_block or stripped_line.startswith("require ")):
                result.append(Dependency(match.group(1), match.group(2)))
        return result

    @GeneralUtilities.check_arguments
    def get_available_versions(self, dependencyname: str) -> list[str]:
        # The go-module-proxy answers with the published versions of a module, one version per line.
        response = requests.get(f"https://proxy.golang.org/{dependencyname.lower()}/@v/list", timeout=60)
        response.raise_for_status()
        result: list[str] = []
        for line in GeneralUtilities.string_to_lines(response.text):
            match = re.match(r"^v(\d+\.\d+\.\d+)$", line.strip())
            if match is not None:
                result.append(match.group(1))
        return result

    @GeneralUtilities.check_arguments
    def set_dependency_version(self, name: str, new_version: str) -> None:
        # "go get" is used instead of rewriting the go.mod-file, because it also updates the go.sum-file, which
        # contains the checksums of the dependencies and would make the build fail if it did not match the go.mod-file.
        self.__run_go(f"get {name}@v{new_version}")
        self.__run_go("mod tidy")

class TFCPS_CodeUnitSpecific_Go_CLI:

    @staticmethod
    @GeneralUtilities.check_arguments
    def parse(file: str) -> TFCPS_CodeUnitSpecific_Go_Functions:
        parser = TFCPS_CodeUnitSpecific_Base_CLI.get_base_parser()
        #add custom parameter if desired
        args = parser.parse_args()
        result: TFCPS_CodeUnitSpecific_Go_Functions = TFCPS_CodeUnitSpecific_Go_Functions(file, LogLevel(int(args.verbosity)), args.targetenvironmenttype, not args.nocache, args.ispremerge)
        return result
