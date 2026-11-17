from ..SecurityCheckBase import SecurityCheckBase
from ..SecurityFinding import SecurityFinding, SecurityFindingSeverity
from ..SystemAccessBase import SystemAccessBase


class NonRootAccountsWithUid0Check(SecurityCheckBase):
    """Every account with uid 0 has root-privileges. Attackers add such accounts as backdoor."""

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        return [self.create_finding(SecurityFindingSeverity.High, f"Account \"{user.name}\" has uid 0 (root-privileges).") for user in system.get_users() if user.uid == 0 and user.name != "root"]


class AccountsWithoutPasswordCheck(SecurityCheckBase):
    """An empty password-field in /etc/shadow allows a login without password."""

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        content = system.read_text("/etc/shadow")
        if content is None:
            return []
        result: list[SecurityFinding] = []
        for line in content.splitlines():
            fields = line.split(":")
            if len(fields) >= 2 and fields[0] != "" and fields[1] == "":
                result.append(self.create_finding(SecurityFindingSeverity.High, f"Account \"{fields[0]}\" has an empty password in /etc/shadow (login without password possible)."))
        return result


class DuplicateUidsCheck(SecurityCheckBase):
    """Multiple accounts with the same uid share all permissions, which can be used to hide a backdoor-account."""

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        accounts_by_uid: dict[int, list[str]] = {}
        for user in system.get_users():
            accounts_by_uid.setdefault(user.uid, []).append(user.name)
        return [self.create_finding(SecurityFindingSeverity.Mid, f"Uid {uid} is used by multiple accounts: {', '.join(names)}.") for uid, names in accounts_by_uid.items() if len(names) > 1 and uid != 0]


class SystemAccountsWithLoginShellCheck(SecurityCheckBase):
    """System-accounts (for example www-data) usually have no login-shell. A login-shell can be a sign of a manipulated account."""

    __non_login_shells: tuple[str, ...] = ("nologin", "false", "sync", "shutdown", "halt")

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        minimal_uid = system.get_minimal_uid_of_regular_users()
        result: list[SecurityFinding] = []
        for user in system.get_users():
            shell_name = user.shell.rsplit("/", 1)[-1]
            if 0 < user.uid < minimal_uid and user.shell != "" and shell_name not in SystemAccountsWithLoginShellCheck.__non_login_shells:
                result.append(self.create_finding(SecurityFindingSeverity.Low, f"System-account \"{user.name}\" (uid {user.uid}) has the login-shell \"{user.shell}\"."))
        return result


class SudoersWithoutPasswordCheck(SecurityCheckBase):
    """NOPASSWD-rules allow privilege-escalation without knowing a password."""

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        files: list[str] = []
        if system.is_regular_file("/etc/sudoers"):
            files.append("/etc/sudoers")
        if system.is_folder("/etc/sudoers.d"):
            files.extend(system.list_regular_files_recursively("/etc/sudoers.d"))
        result: list[SecurityFinding] = []
        for file in files:
            content = system.read_text(file)
            if content is None:
                continue
            for line_number, line in enumerate(content.splitlines(), start=1):
                stripped_line = line.strip()
                if not stripped_line.startswith("#") and "NOPASSWD" in stripped_line:
                    result.append(self.create_finding(SecurityFindingSeverity.Low, f"Sudo-rule without password in \"{file}\" line {line_number}: {stripped_line}"))
        return result
