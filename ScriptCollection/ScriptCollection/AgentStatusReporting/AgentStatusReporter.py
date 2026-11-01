from abc import ABC, abstractmethod
from .AgentStatus import AgentStatus


class AgentStatusReporter(ABC):
    """Receives the state of the agent. An implementation must not raise on a failed report, because the agent has to keep running in that case."""

    @abstractmethod
    def report(self, status: AgentStatus) -> None:
        raise NotImplementedError

    @abstractmethod
    def release(self) -> None:
        raise NotImplementedError
