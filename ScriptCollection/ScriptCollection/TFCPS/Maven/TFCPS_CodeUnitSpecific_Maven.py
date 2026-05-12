from ...GeneralUtilities import GeneralUtilities
from ...SCLog import LogLevel
from ..TFCPS_CodeUnitSpecific_Base import TFCPS_CodeUnitSpecific_Base, TFCPS_CodeUnitSpecific_Base_CLI

class TFCPS_CodeUnitSpecific_Maven_Functions(TFCPS_CodeUnitSpecific_Base):

    def __init__(self, current_file: str, verbosity: LogLevel, targetenvironmenttype: str, use_cache: bool, is_pre_merge: bool):
        super().__init__(current_file, verbosity, targetenvironmenttype, use_cache, is_pre_merge)

    @GeneralUtilities.check_arguments
    def build(self) -> None:
        pass#TODO

    @GeneralUtilities.check_arguments
    def linting(self) -> None:
        pass#TODO

    @GeneralUtilities.check_arguments
    def run_testcases(self) -> None:
        pass#TODO

    def get_dependencies(self) -> dict[str, set[str]]:
        return dict[str, set[str]]()#TODO

    @GeneralUtilities.check_arguments
    def get_available_versions(self, dependencyname: str) -> list[str]:
        return []#TODO

    @GeneralUtilities.check_arguments
    def set_dependency_version(self, name: str, new_version: str) -> None:
        raise ValueError("Operation is not implemented.")

class TFCPS_CodeUnitSpecific_Maven_CLI:

    @staticmethod
    @GeneralUtilities.check_arguments
    def parse(file: str) -> TFCPS_CodeUnitSpecific_Maven_Functions:
        parser = TFCPS_CodeUnitSpecific_Base_CLI.get_base_parser()
        #add custom parameter if desired
        args = parser.parse_args()
        result: TFCPS_CodeUnitSpecific_Maven_Functions = TFCPS_CodeUnitSpecific_Maven_Functions(file, LogLevel(int(args.verbosity)), args.targetenvironmenttype, not args.nocache, args.ispremerge)
        return result
