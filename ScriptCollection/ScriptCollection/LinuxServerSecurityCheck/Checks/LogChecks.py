from ..SecurityCheckBase import SecurityCheckBase
from ..SecurityFinding import SecurityFinding, SecurityFindingSeverity
from ..SystemAccessBase import SystemAccessBase


class RedirectedShellHistoriesCheck(SecurityCheckBase):
    """Attackers link the shell-history to /dev/null to hide their commands."""

    history_files: list[str] = [".bash_history", ".zsh_history", ".sh_history", ".ash_history", ".history"]

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        result: list[SecurityFinding] = []
        for home_folder in system.get_home_folders():
            for history_file in RedirectedShellHistoriesCheck.history_files:
                path = f"{home_folder.rstrip('/')}/{history_file}"
                if system.is_symlink(path):
                    target = system.read_link(path)
                    if target == "/dev/null":
                        result.append(self.create_finding(SecurityFindingSeverity.Mid, f"Shell-history \"{path}\" is linked to /dev/null."))
        return result


class EmptyLoginRecordsCheck(SecurityCheckBase):
    """Attackers clear the login-records to hide their logins.
    Because logrotate creates an empty file when it rotates, an empty file is only reported if no rotated file exists."""

    login_record_files: list[str] = ["/var/log/wtmp", "/var/log/lastlog"]

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        result: list[SecurityFinding] = []
        for path in EmptyLoginRecordsCheck.login_record_files:
            file_stat = system.get_lstat(path)
            if file_stat is not None and file_stat.st_size == 0 and not self.__rotated_file_exists(system, path):
                result.append(self.create_finding(SecurityFindingSeverity.Mid, f"Login-records \"{path}\" are empty although they were never rotated."))
        return result

    def __rotated_file_exists(self, system: SystemAccessBase, path: str) -> bool:
        folder, file_name = path.rsplit("/", 1)
        return any(entry != file_name and entry.startswith(file_name + ".") for entry in system.list_folder(folder) or [])
