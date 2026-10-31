import subprocess
import time
from ..GeneralUtilities import GeneralUtilities
from .AgentStatus import AgentStatus
from .AgentStatusReporter import AgentStatusReporter


class HerdrAgentStatusReporter(AgentStatusReporter):
    """Reports the state of the agent with the herdr-CLI."""
    source: str = "scrais"
    timeout_in_seconds: int = 5
    __herdr_program: str = None
    __pane_id: str = None
    __agent_name: str = None
    __verbose: bool = None
    __last_sequence_number: int = 0

    @GeneralUtilities.check_arguments
    def __init__(self, herdr_program: str, pane_id: str, agent_name: str, verbose: bool):
        self.__herdr_program = herdr_program
        self.__pane_id = pane_id
        self.__agent_name = agent_name
        self.__verbose = verbose
        self.__last_sequence_number = 0

    @staticmethod
    @GeneralUtilities.check_arguments
    def try_create(environment: dict[str, str], agent_name: str, verbose: bool) -> "HerdrAgentStatusReporter":
        # Returns None if scrais does not run in a herdr-pane.
        pane_id = environment.get("HERDR_PANE_ID")
        herdr_program = environment.get("HERDR_BIN_PATH")
        if environment.get("HERDR_ENV") != "1" or not pane_id or not herdr_program:
            return None
        return HerdrAgentStatusReporter(herdr_program, pane_id, agent_name, verbose)

    @GeneralUtilities.check_arguments
    def get_report_command(self, status: AgentStatus) -> list[str]:
        return [self.__herdr_program, "pane", "report-agent", self.__pane_id, "--source", self.source, "--agent", self.__agent_name, "--state", status.value, "--seq", str(self.__get_next_sequence_number())]

    @GeneralUtilities.check_arguments
    def get_release_command(self) -> list[str]:
        return [self.__herdr_program, "pane", "release-agent", self.__pane_id, "--source", self.source, "--agent", self.__agent_name, "--seq", str(self.__get_next_sequence_number())]

    @GeneralUtilities.check_arguments
    def report(self, status: AgentStatus) -> None:
        self.__run(self.get_report_command(status))

    @GeneralUtilities.check_arguments
    def release(self) -> None:
        self.__run(self.get_release_command())

    @GeneralUtilities.check_arguments
    def __get_next_sequence_number(self) -> int:
        # time_ns makes the number increase across runs; the comparison keeps it strictly increasing if the resolution of the clock is too coarse for two reports in quick succession.
        self.__last_sequence_number = max(time.time_ns(), self.__last_sequence_number + 1)
        return self.__last_sequence_number

    @GeneralUtilities.check_arguments
    def __run(self, command: list[str]) -> None:
        # The command is an argument-list without shell, so that paths with spaces work and nothing can be injected.
        # Stdin and the output are detached, because the terminal belongs to the agent.
        try:
            result = subprocess.run(command, check=False, stdin=subprocess.DEVNULL, capture_output=True, timeout=self.timeout_in_seconds)
            if result.returncode != 0:
                self.__write_failure(f"exit-code {result.returncode}")
        except (OSError, subprocess.SubprocessError) as exception:
            self.__write_failure(str(exception))

    @GeneralUtilities.check_arguments
    def __write_failure(self, reason: str) -> None:
        if self.__verbose:
            GeneralUtilities.write_message_to_stderr(f"Reporting the agent-status to herdr failed: {reason}")
