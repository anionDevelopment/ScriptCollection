import threading
from ..GeneralUtilities import GeneralUtilities
from .AgentStatus import AgentStatus
from .AgentStatusReporter import AgentStatusReporter


class AgentStatusRelay:
    """Forwards the valid states from the event-file to a reporter. The file is written by the container, so its content is untrusted.
    To limit what a container can cause, a read is limited in size and it results in at most one report, which is the latest state of that read."""
    poll_interval_in_seconds: float = 0.25
    maximal_line_length: int = 64
    maximal_read_size: int = 65536
    __events_file: str = None
    __reporter: AgentStatusReporter = None
    __verbose: bool = None
    __offset: int = 0
    __unfinished_line: bytes = b""
    __skip_rest_of_line: bool = False
    __last_status: AgentStatus = None
    __stop_requested: threading.Event = None
    __thread: threading.Thread = None

    @GeneralUtilities.check_arguments
    def __init__(self, events_file: str, reporter: AgentStatusReporter, verbose: bool):
        self.__events_file = events_file
        self.__reporter = reporter
        self.__verbose = verbose
        self.__offset = 0
        self.__unfinished_line = b""
        self.__skip_rest_of_line = False
        self.__last_status = None
        self.__stop_requested = threading.Event()
        self.__thread = threading.Thread(target=self.__poll, daemon=True)

    @GeneralUtilities.check_arguments
    def has_reported(self) -> bool:
        return self.__last_status is not None

    @GeneralUtilities.check_arguments
    def start(self) -> None:
        self.__thread.start()

    @GeneralUtilities.check_arguments
    def stop(self) -> None:
        # The final read gets what the agent has written between the last poll and the end of the container.
        self.__stop_requested.set()
        if self.__thread.is_alive():
            self.__thread.join()
        self.process_new_events()

    @GeneralUtilities.check_arguments
    def process_new_events(self) -> None:
        status = self.__read_latest_status()
        if status is not None and status != self.__last_status:
            self.__last_status = status
            self.__reporter.report(status)

    @GeneralUtilities.check_arguments
    def __poll(self) -> None:
        try:
            while not self.__stop_requested.wait(self.poll_interval_in_seconds):
                self.process_new_events()
        except Exception as exception:  # pylint: disable=broad-exception-caught
            # This runs in an own thread beside the agent, so a failure only ends the reporting.
            if self.__verbose:
                GeneralUtilities.write_message_to_stderr(f"Reading the agent-status failed: {exception}")

    @GeneralUtilities.check_arguments
    def __read_latest_status(self) -> AgentStatus:
        with open(self.__events_file, "rb") as events_file:
            events_file.seek(self.__offset)
            new_content = events_file.read(self.maximal_read_size)
        self.__offset = self.__offset + len(new_content)
        lines = (self.__unfinished_line + new_content).split(b"\n")
        self.__unfinished_line = lines.pop()
        latest_status: AgentStatus = None
        for line in lines:
            if self.__skip_rest_of_line:
                self.__skip_rest_of_line = False
                continue
            status = AgentStatus.parse_token(line)
            if status is not None:
                latest_status = status
        if self.maximal_line_length < len(self.__unfinished_line):
            self.__unfinished_line = b""
            self.__skip_rest_of_line = True
        return latest_status
