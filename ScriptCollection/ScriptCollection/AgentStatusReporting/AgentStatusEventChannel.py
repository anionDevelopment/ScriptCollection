import os
import tempfile
from ..GeneralUtilities import GeneralUtilities
from .AgentStatus import AgentStatus


class AgentStatusEventChannel:
    """The channel from the container to the host: one event-file in a dedicated host-folder which is mounted into the container."""
    container_folder: str = "/Workspace/Temp/AgentStatus"
    status_helper: str = "scrais-agent-status"
    __host_folder: str = None

    @GeneralUtilities.check_arguments
    def __init__(self):
        self.__host_folder = tempfile.mkdtemp(prefix="ScraisAgentStatus")
        # The user of the container is unknown and it can be a user without the capability to bypass file-permissions (see drop_capabilities), so everybody must be able to write.
        os.chmod(self.__host_folder, 0o777)
        GeneralUtilities.ensure_file_exists(self.get_events_file())
        os.chmod(self.get_events_file(), 0o666)

    @GeneralUtilities.check_arguments
    def get_events_file(self) -> str:
        return os.path.join(self.__host_folder, "events")

    @GeneralUtilities.check_arguments
    def get_volume_arguments(self) -> list[str]:
        return ["--volume", f"{self.__host_folder.replace(os.sep, '/')}:{self.container_folder}"]

    @GeneralUtilities.check_arguments
    def get_start_report_line(self, status: AgentStatus) -> str:
        # An image without the status-helper does not report anything. The "|| true" prevents that this line can stop the entrypoint, which runs with "set -e".
        return f"command -v {self.status_helper} >/dev/null 2>&1 && {self.status_helper} {status.value} || true"

    @GeneralUtilities.check_arguments
    def remove(self) -> None:
        GeneralUtilities.ensure_directory_does_not_exist(self.__host_folder)
