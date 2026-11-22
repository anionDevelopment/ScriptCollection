from dataclasses import dataclass
from enum import Enum


class SecurityFindingSeverity(Enum):
    High = "High"
    Mid = "Mid"
    Low = "Low"


@dataclass(frozen=True)
class SecurityFinding:
    check_name: str
    severity: SecurityFindingSeverity
    message: str

    def to_line(self) -> str:
        single_line_message = " ".join(self.message.splitlines())
        return f"[{self.severity.value}] [{self.check_name}] {single_line_message}"
