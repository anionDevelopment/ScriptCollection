from ..GeneralUtilities import GeneralUtilities
from .AgentStatus import AgentStatus
from .AgentStatusEventChannel import AgentStatusEventChannel
from .AgentStatusRelay import AgentStatusRelay
from .AgentStatusReporter import AgentStatusReporter
from .HerdrAgentStatusReporter import HerdrAgentStatusReporter


class AgentStatusReportingSession:
    """The status-report of one run of a container. It knows no concrete coding-agent: the image connects its agents to the channel.
    Nothing in here can stop the agent: a failure disables the report for this run and is shown in verbose output only."""
    __channel: AgentStatusEventChannel = None
    __relay: AgentStatusRelay = None
    __reporter: AgentStatusReporter = None
    __verbose: bool = None

    @GeneralUtilities.check_arguments
    def __init__(self, channel: AgentStatusEventChannel, relay: AgentStatusRelay, reporter: AgentStatusReporter, verbose: bool):
        self.__channel = channel
        self.__relay = relay
        self.__reporter = reporter
        self.__verbose = verbose

    @staticmethod
    @GeneralUtilities.check_arguments
    def try_create(environment: dict[str, str], agent_name: str, verbose: bool) -> "AgentStatusReportingSession":
        # Returns None if there is nothing to report to or if the channel can not be created.
        reporter = HerdrAgentStatusReporter.try_create(environment, agent_name, verbose)
        if reporter is None:
            return None
        try:
            channel = AgentStatusEventChannel()
        except OSError as exception:
            AgentStatusReportingSession.__write_verbose_message(verbose, f"The agent-status is not reported because its channel can not be created: {exception}")
            return None
        return AgentStatusReportingSession(channel, AgentStatusRelay(channel.get_events_file(), reporter, verbose), reporter, verbose)

    @GeneralUtilities.check_arguments
    def get_volume_arguments(self) -> list[str]:
        return self.__channel.get_volume_arguments()

    @GeneralUtilities.check_arguments
    def get_start_report_line(self, prompt_is_given: bool) -> str:
        return self.__channel.get_start_report_line(AgentStatus.Working if prompt_is_given else AgentStatus.Idle)

    @GeneralUtilities.check_arguments
    def start(self) -> None:
        try:
            self.__relay.start()
        except RuntimeError as exception:
            AgentStatusReportingSession.__write_verbose_message(self.__verbose, f"The agent-status is not reported because reading it can not be started: {exception}")

    @GeneralUtilities.check_arguments
    def stop(self) -> None:
        try:
            self.__finish()
        except Exception as exception:  # pylint: disable=broad-exception-caught
            # This runs after the agent has ended, so a failure must not replace its exit-code.
            AgentStatusReportingSession.__write_verbose_message(self.__verbose, f"Finishing the report of the agent-status failed: {exception}")

    @GeneralUtilities.check_arguments
    def __finish(self) -> None:
        try:
            self.__relay.stop()
            if self.__relay.has_reported():
                self.__reporter.release()
            else:
                AgentStatusReportingSession.__write_verbose_message(self.__verbose, f"No agent-status was received. An image only reports the status if it contains '{AgentStatusEventChannel.status_helper}'.")
        finally:
            self.__channel.remove()

    @staticmethod
    @GeneralUtilities.check_arguments
    def __write_verbose_message(verbose: bool, message: str) -> None:
        if verbose:
            GeneralUtilities.write_message_to_stderr(message)
