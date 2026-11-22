from abc import ABC, abstractmethod
from .SecurityFinding import SecurityFinding, SecurityFindingSeverity
from .SystemAccessBase import SystemAccessBase


class SecurityCheckBase(ABC):
    """Base-class of all checks. A check only reads the system and must not change anything.
    To add a new check: derive from this class, implement "run" and add an instance to LinuxServerSecurityChecker.get_default_checks."""

    def get_name(self) -> str:
        class_name = type(self).__name__
        return class_name.removesuffix("Check")

    @abstractmethod
    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        raise NotImplementedError

    def create_finding(self, severity: SecurityFindingSeverity, message: str) -> SecurityFinding:
        return SecurityFinding(self.get_name(), severity, message)
