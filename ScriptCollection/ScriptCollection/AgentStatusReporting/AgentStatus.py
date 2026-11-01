from enum import Enum


class AgentStatus(Enum):
    """The closed vocabulary of the channel between the container and the host."""
    Working = "working"
    Idle = "idle"
    Blocked = "blocked"

    @staticmethod
    def parse_token(line: bytes) -> "AgentStatus":
        # The line comes from a file which the container can write, so it is untrusted: only an exact token is accepted and everything else results in None.
        for status in AgentStatus:
            if line == status.value.encode("ascii"):
                return status
        return None
