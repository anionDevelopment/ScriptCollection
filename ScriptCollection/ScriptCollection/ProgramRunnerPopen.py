import os
import sys
from subprocess import PIPE, Popen
from .GeneralUtilities import GeneralUtilities
from .ProgramRunnerBase import ProgramRunnerBase


class ProgramRunnerPopen(ProgramRunnerBase):

    @GeneralUtilities.check_arguments
    def run_program_argsasarray_async_helper(self, program: str, arguments_as_array: list[str] = [], working_directory: str = None, custom_argument: object = None, interactive: bool = False, env_vars: dict = None) -> Popen:
        arguments_for_process = [program]
        arguments_for_process.extend(arguments_as_array)
        # "shell=True" is not allowed because it is not recommended and also something like
        # "ScriptCollectionCore().run_program('curl', 'https://example.com/dataset?id=1&format=json')"
        # would not be possible anymore because the ampersand will be treated as shell-command.
        env = {**os.environ, **env_vars} if env_vars is not None else None
        try:
            if interactive:
                result = Popen(arguments_for_process, cwd=working_directory, stdout=PIPE, stderr=PIPE, shell=False, text=True, stdin=sys.stdin, env=env)  # pylint: disable=consider-using-with
            else:
                result = Popen(arguments_for_process, cwd=working_directory, stdout=PIPE, stderr=PIPE, shell=False, text=True, env=env)  # pylint: disable=consider-using-with
        except FileNotFoundError as fileNotFoundError:
            raise FileNotFoundError(f"Starting '{program}' in '{working_directory}' resulted in a FileNotFoundError: '{str(fileNotFoundError)}'")
        except NotADirectoryError as notADirectoryError:
            raise NotADirectoryError(f"Starting '{program}' in '{working_directory}' resulted in a NotADirectoryError: '{str(notADirectoryError)}'")
        return result

    # Return-values program_runner: Exitcode, StdOut, StdErr, Pid
    @GeneralUtilities.check_arguments
    def wait(self, process: Popen, custom_argument: object) -> tuple[int, str, str, int]:
        pid = process.pid
        stdout, stderr = process.communicate()
        exit_code = process.wait()
        stdout = GeneralUtilities.bytes_to_string(stdout).replace('\r', '')
        stderr = GeneralUtilities.bytes_to_string(stderr).replace('\r', '')
        result = (exit_code, stdout, stderr, pid)
        return result

    @GeneralUtilities.check_arguments
    def run_program_argsasarray(self, program: str, arguments_as_array: list[str] = [], working_directory: str = None, custom_argument: object = None, interactive: bool = False, env_vars: dict = None) -> tuple[int, str, str, int]:
        process: Popen = self.run_program_argsasarray_async_helper(program, arguments_as_array, working_directory, custom_argument, interactive, env_vars)
        return self.wait(process, custom_argument)

    @GeneralUtilities.check_arguments
    def run_program(self, program: str, arguments: str = "", working_directory: str = None, custom_argument: object = None, interactive: bool = False, env_vars: dict = None) -> tuple[int, str, str, int]:
        return self.run_program_argsasarray(program, GeneralUtilities.arguments_to_array(arguments), working_directory, custom_argument, interactive, env_vars)

    @GeneralUtilities.check_arguments
    def run_program_argsasarray_async(self, program: str, arguments_as_array: list[str] = [], working_directory: str = None, custom_argument: object = None, interactive: bool = False, env_vars: dict = None) -> int:
        return self.run_program_argsasarray_async_helper(program, arguments_as_array, working_directory, custom_argument, interactive, env_vars).pid

    @GeneralUtilities.check_arguments
    def run_program_async(self, program: str, arguments: str = "", working_directory: str = None, custom_argument: object = None, interactive: bool = False, env_vars: dict = None) -> int:
        return self.run_program_argsasarray_async(program, GeneralUtilities.arguments_to_array(arguments), working_directory, custom_argument, interactive, env_vars)

    @GeneralUtilities.check_arguments
    def will_be_executed_locally(self) -> bool:
        return True
