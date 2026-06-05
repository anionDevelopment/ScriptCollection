from subprocess import Popen
from .GeneralUtilities import GeneralUtilities
from .ProgramRunnerBase import ProgramRunnerBase
from .ScriptCollectionCore import ScriptCollectionCore


class SudoPopenReader:
    content: bytes = None

    def __init__(self, content: bytes):
        self.content = content

    def readable(self) -> bool:
        return True

    def read(self) -> bytes:
        return self.content


class SudoPopen:
    returncode: int = None
    stdout_str: str = None
    stderr_str: str = None
    pid: int = None
    stdout: bytes = None
    stderr: bytes = None

    def __init__(self, exitcode: int, stdout: str, stderr: str, pid: int):
        self.returncode: int = exitcode
        self.stdout_str: str = stdout
        self.stdout = str.encode(self.stdout_str)
        self.stderr_str: str = stderr
        self.stderr = str.encode(self.stderr_str)
        self.pid = pid

    def communicate(self):
        return (self.stdout, self.stderr)

    def wait(self):
        return self.returncode

    def poll(self) -> object:
        return self.returncode

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass


class ProgramRunnerSudo(ProgramRunnerBase):
    __sc: ScriptCollectionCore
    __password: str

    @GeneralUtilities.check_arguments
    def __init__(self,user_password:str):
        GeneralUtilities.assert_condition(GeneralUtilities.current_system_is_linux(), "SudoRunner can only be only executed on Linux.")
        self.__sc = ScriptCollectionCore()
        self.__password = user_password

    @GeneralUtilities.check_arguments
    def will_be_executed_locally(self) -> bool:
        return True

    @GeneralUtilities.check_arguments
    def run_program_internal(self, program: str, arguments_as_array: list[str] = [], working_directory: str = None, custom_argument: object = None, env_vars: dict = None) -> tuple[int, str, str, int]:
        if env_vars is not None:
            raise ValueError("env_vars is not supported in Sudo-runner")
        argument = program+" " + ' '.join(GeneralUtilities.args_array_surround_with_quotes_if_required(arguments_as_array))
        argument = f"echo {self.__password} | sudo -k -S {argument}"  # TODO maybe add "exit" somewhere before argument or before sudo to correctly return the exit-code"
        result = self.__sc.run_program_argsasarray("sh", ["-c", argument], working_directory)
        return result

    @GeneralUtilities.check_arguments
    def run_program_argsasarray_async_helper(self, program: str, arguments_as_array: list[str] = [], working_directory: str = None, custom_argument: object = None, interactive: bool = False, env_vars: dict = None) -> Popen:
        if interactive:
            raise ValueError("Interactive execution is not supported in Sudo-runner")
        r: tuple[int, str, str, int] = self.run_program_internal(program, arguments_as_array, working_directory, custom_argument, env_vars)
        popen: SudoPopen = SudoPopen(r[0], r[1], r[2], r[3])
        return popen

    # Return-values program_runner: Exitcode, StdOut, StdErr, Pid
    @GeneralUtilities.check_arguments
    def wait(self, process: Popen, custom_argument: object) -> tuple[int, str, str, int]:
        raise ValueError("Wait is not supported in Sudo-runner")

    # Return-values program_runner: Exitcode, StdOut, StdErr, Pid
    @GeneralUtilities.check_arguments
    def run_program_argsasarray(self, program: str, arguments_as_array: list[str] = [], working_directory: str = None, custom_argument: object = None, interactive: bool = False, env_vars: dict = None) -> tuple[int, str, str, int]:
        if interactive:
            raise ValueError("Interactive execution is not supported in Sudo-runner")
        return self.run_program_internal(program, arguments_as_array, working_directory, custom_argument, env_vars)

    # Return-values program_runner: Exitcode, StdOut, StdErr, Pid
    @GeneralUtilities.check_arguments
    def run_program(self, program: str, arguments:  str = "", working_directory: str = None, custom_argument: object = None, interactive: bool = False, env_vars: dict = None) -> tuple[int, str, str, int]:
        if interactive:
            raise ValueError("Interactive execution is not supported in Sudo-runner")
        return self.run_program_internal(program, arguments.split(" "), working_directory, custom_argument, env_vars)

    # Return-values program_runner: Pid
    @GeneralUtilities.check_arguments
    def run_program_argsasarray_async(self, program: str, arguments_as_array: list[str] = [], working_directory: str = None, custom_argument: object = None, interactive: bool = False, env_vars: dict = None) -> int:
        raise ValueError("Async execution is not supported in Sudo-runner")

    # Return-values program_runner: Pid
    @GeneralUtilities.check_arguments
    def run_program_async(self, program: str, arguments: str,  working_directory: str, custom_argument: object, interactive: bool = False, env_vars: dict = None) -> int:
        raise ValueError("Async execution is not supported in Sudo-runner")
