import re
from dataclasses import dataclass
from .SecurityFinding import SecurityFindingSeverity


@dataclass(frozen=True)
class SuspiciousCommandPattern:
    description: str
    regex: re.Pattern[str]
    severity: SecurityFindingSeverity


class SuspiciousCommandPatterns:
    """Patterns of commands which are typical for attackers (download-and-execute, reverse-shells, crypto-miners, hiding of traces)."""

    temporary_folders: tuple[str, ...] = ("/tmp/", "/var/tmp/", "/dev/shm/")
    """Folders which are writable for everybody and which are therefore typically used by attackers to drop their tools."""

    __shell = r"(sudo\s+)?(/usr)?(/bin/)?(ba|da|z|k)?sh\b"
    __patterns: list[SuspiciousCommandPattern] = [
        SuspiciousCommandPattern("download piped into a shell", re.compile(r"\b(curl|wget)\b[^|;&\n]*\|\s*" + __shell, re.IGNORECASE), SecurityFindingSeverity.High),
        SuspiciousCommandPattern("base64-decoded content piped into a shell", re.compile(r"\bbase64\s+(-d|--decode)\b[^\n]*\|\s*" + __shell, re.IGNORECASE), SecurityFindingSeverity.High),
        SuspiciousCommandPattern("network-connection via /dev/tcp or /dev/udp (reverse-shell)", re.compile(r"/dev/(tcp|udp)/", re.IGNORECASE), SecurityFindingSeverity.High),
        SuspiciousCommandPattern("netcat executing a program (reverse-shell)", re.compile(r"\b(nc|ncat|netcat)\b[^\n|;&]*\s-(e|c)\s", re.IGNORECASE), SecurityFindingSeverity.High),
        SuspiciousCommandPattern("socat executing a program (reverse-shell)", re.compile(r"\bsocat\b[^\n]*\b(exec|system):", re.IGNORECASE), SecurityFindingSeverity.High),
        SuspiciousCommandPattern("interactive shell with redirected input/output (reverse-shell)", re.compile(r"\b(ba|z)?sh\s+-i\b[^\n]*[<>]&", re.IGNORECASE), SecurityFindingSeverity.High),
        SuspiciousCommandPattern("scripting-language opening a socket (reverse-shell)", re.compile(r"\b(python[0-9.]*|perl|ruby|php)\s+-(c|e|r)\s+[^\n]*\bsocket\b", re.IGNORECASE), SecurityFindingSeverity.High),
        SuspiciousCommandPattern("crypto-mining-pool-protocol", re.compile(r"\bstratum\+(tcp|ssl|tls)://", re.IGNORECASE), SecurityFindingSeverity.High),
        SuspiciousCommandPattern("known crypto-miner or malware", re.compile(r"\b(xmrig|xmr-stak|minerd|cpuminer|kdevtmpfsi|kinsing|kthreaddk)\b", re.IGNORECASE), SecurityFindingSeverity.High),
        SuspiciousCommandPattern("hidden file in a temporary folder", re.compile(r"(?<![\w.])(/tmp|/var/tmp|/dev/shm)/\.(?!(X11-unix|ICE-unix|font-unix|XIM-unix|Test-unix)\b)[^\s/\"']", re.IGNORECASE), SecurityFindingSeverity.Mid),
        SuspiciousCommandPattern("making a file immutable", re.compile(r"\bchattr\s+[^\n]*\+[a-z]*i", re.IGNORECASE), SecurityFindingSeverity.Mid),
        SuspiciousCommandPattern("disabling the shell-history", re.compile(r"\bHISTFILE=/dev/null|\bunset\s+HISTFILE\b|\bHISTSIZE=0\b|\bhistory\s+-c\b"), SecurityFindingSeverity.Mid),
        SuspiciousCommandPattern("preloading a library", re.compile(r"\bLD_PRELOAD="), SecurityFindingSeverity.Mid),
    ]

    @staticmethod
    def find_matches(text: str) -> list[SuspiciousCommandPattern]:
        return [pattern for pattern in SuspiciousCommandPatterns.__patterns if pattern.regex.search(text) is not None]  # pylint:disable=no-member  # false positive of pylint for re.Pattern-fields of dataclasses

    @staticmethod
    def is_in_temporary_folder(path: str) -> bool:
        return path.startswith(SuspiciousCommandPatterns.temporary_folders)

    @staticmethod
    def contains_hidden_path_component(path: str) -> bool:
        return any(part.startswith(".") and part not in (".", "..") for part in path.split("/"))
