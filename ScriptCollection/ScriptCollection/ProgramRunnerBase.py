from abc import abstractmethod
from subprocess import Popen
from .GeneralUtilities import GeneralUtilities


class ProgramRunnerBase:

    # Return-values program_runner: Pid
    @abstractmethod
    @GeneralUtilities.check_arguments
    def run_program_argsasarray_async_helper(self, program: str, arguments_as_array: list[str] = [], working_directory: str = None, custom_argument: object = None, interactive: bool = False, env_vars: dict = None) -> Popen:
        raise NotImplementedError

    # Return-values program_runner: Exitcode, StdOut, StdErr, Pid
    @abstractmethod
    @GeneralUtilities.check_arguments
    def wait(self, process: Popen, custom_argument: object) -> tuple[int, str, str, int]:
        raise NotImplementedError

    # Return-values program_runner: Exitcode, StdOut, StdErr, Pid
    @abstractmethod
    @GeneralUtilities.check_arguments
    def run_program_argsasarray(self, program: str, arguments_as_array: list[str] = [], working_directory: str = None, custom_argument: object = None, interactive: bool = False, env_vars: dict = None) -> tuple[int, str, str, int]:
        raise NotImplementedError

    # Return-values program_runner: Exitcode, StdOut, StdErr, Pid
    @abstractmethod
    @GeneralUtilities.check_arguments
    def run_program(self, program: str, arguments:  str = "", working_directory: str = None, custom_argument: object = None, interactive: bool = False, env_vars: dict = None) -> tuple[int, str, str, int]:
        raise NotImplementedError

    # Return-values program_runner: Pid
    @abstractmethod
    @GeneralUtilities.check_arguments
    def run_program_argsasarray_async(self, program: str, arguments_as_array: list[str] = [], working_directory: str = None, custom_argument: object = None, interactive: bool = False, env_vars: dict = None) -> int:
        raise NotImplementedError

    # Return-values program_runner: Pid
    @abstractmethod
    @GeneralUtilities.check_arguments
    def run_program_async(self, program: str, arguments: str,  working_directory: str, custom_argument: object, interactive: bool = False, env_vars: dict = None) -> int:
        raise NotImplementedError

    @abstractmethod
    @GeneralUtilities.check_arguments
    def will_be_executed_locally(self) -> bool:
        raise NotImplementedError
