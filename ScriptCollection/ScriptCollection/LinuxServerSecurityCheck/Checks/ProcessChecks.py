import re
from ..SecurityCheckBase import SecurityCheckBase
from ..SecurityFinding import SecurityFinding, SecurityFindingSeverity
from ..SuspiciousCommandPatterns import SuspiciousCommandPatterns
from ..SystemAccessBase import SystemAccessBase


class ProcessesRunningFromTemporaryFoldersCheck(SecurityCheckBase):
    """Legitimate software is not executed from world-writable temporary folders or from hidden folders, but dropped malware often is."""

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        result: list[SecurityFinding] = []
        for process in system.get_processes():
            if process.executable is None:
                continue
            if SuspiciousCommandPatterns.is_in_temporary_folder(process.executable):
                result.append(self.create_finding(SecurityFindingSeverity.High, f"Process runs from a temporary folder: {process.describe()}"))
            elif SuspiciousCommandPatterns.contains_hidden_path_component(process.executable):
                result.append(self.create_finding(SecurityFindingSeverity.High, f"Process runs from a hidden path: {process.describe()}"))
        return result


class ProcessesWithDeletedExecutableCheck(SecurityCheckBase):
    """Malware often deletes its executable after it was started.
    A deleted executable can also be caused by a package-update without a restart of the process; in this case a new file exists at the same path."""

    __deleted_suffix: str = " (deleted)"

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        result: list[SecurityFinding] = []
        for process in system.get_processes():
            if process.executable is None or not process.executable.endswith(ProcessesWithDeletedExecutableCheck.__deleted_suffix):
                continue
            original_path = process.executable[:-len(ProcessesWithDeletedExecutableCheck.__deleted_suffix)]
            if SuspiciousCommandPatterns.is_in_temporary_folder(original_path) or SuspiciousCommandPatterns.contains_hidden_path_component(original_path):
                continue  # already reported by ProcessesRunningFromTemporaryFoldersCheck
            # /proc/<pid>/root resolves the path in the mount-namespace of the process, which is relevant for processes in containers.
            if system.path_exists(f"/proc/{process.pid}/root{original_path}"):
                result.append(self.create_finding(SecurityFindingSeverity.Low, f"Executable of process was replaced (probably by an update without restart): {process.describe()}"))
            else:
                result.append(self.create_finding(SecurityFindingSeverity.Mid, f"Executable of process was deleted and not replaced: {process.describe()}"))
        return result


class ProcessesMasqueradingAsKernelThreadsCheck(SecurityCheckBase):
    """Kernel-threads are shown in brackets (for example "[kworker/0:1]") and have no executable.
    A user-space-process which names itself like that tries to hide."""

    __kernel_thread_name_pattern = re.compile(r"^\[[^\]\s]+\]")

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        result: list[SecurityFinding] = []
        for process in system.get_processes():
            if process.executable is not None and ProcessesMasqueradingAsKernelThreadsCheck.__kernel_thread_name_pattern.match(process.commandline):
                result.append(self.create_finding(SecurityFindingSeverity.High, f"User-space-process disguises itself as kernel-thread: {process.describe()}"))
        return result


class SuspiciousProcessCommandlinesCheck(SecurityCheckBase):
    """Detects reverse-shells, crypto-miners and similar based on the commandline and the name of the running processes."""

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        result: list[SecurityFinding] = []
        for process in system.get_processes():
            if process.is_kernel_thread_or_zombie():
                continue
            text = f"{process.name} {process.executable} {process.commandline}"
            for pattern in SuspiciousCommandPatterns.find_matches(text):
                result.append(self.create_finding(pattern.severity, f"Suspicious process ({pattern.description}): {process.describe()}"))
        return result


class ProcessesWithPreloadedLibrariesCheck(SecurityCheckBase):
    """LD_PRELOAD injects a library into a process, which is a common technique of user-space-rootkits."""

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        result: list[SecurityFinding] = []
        for process in system.get_processes():
            if process.is_kernel_thread_or_zombie():
                continue
            environment = system.read_bytes(f"/proc/{process.pid}/environ", SystemAccessBase.maximal_size_of_text_files)
            if environment is None:
                continue
            for variable in environment.split(b"\0"):
                if variable.startswith(b"LD_PRELOAD=") and len(variable) > len(b"LD_PRELOAD="):
                    value = variable.decode("utf-8", errors="replace")
                    result.append(self.create_finding(SecurityFindingSeverity.Mid, f"Process has {value}: {process.describe()}"))
        return result
