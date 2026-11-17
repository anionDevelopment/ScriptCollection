from ..SecurityCheckBase import SecurityCheckBase
from ..SecurityFinding import SecurityFinding, SecurityFindingSeverity
from ..SystemAccessBase import SystemAccessBase


class SshServerConfigurationCheck(SecurityCheckBase):
    """Checks the effective configuration of the ssh-server (as reported by "sshd -T")."""

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        if not system.program_is_available("sshd"):
            return []
        program_result = system.run_program("sshd", ["-T"])
        if program_result.exit_code != 0:
            raise ValueError(f"\"sshd -T\" failed with exitcode {program_result.exit_code}: {program_result.stderr.strip()}")
        configuration: dict[str, str] = {}
        for line in program_result.stdout.splitlines():
            fields = line.strip().split(" ", 1)
            if len(fields) == 2:
                configuration[fields[0].lower()] = fields[1].strip().lower()
        result: list[SecurityFinding] = []
        if configuration.get("permitemptypasswords") == "yes":
            result.append(self.create_finding(SecurityFindingSeverity.High, "ssh-server allows logins with empty passwords (PermitEmptyPasswords yes)."))
        if configuration.get("permitrootlogin") == "yes":
            result.append(self.create_finding(SecurityFindingSeverity.Mid, "ssh-server allows root-logins with password (PermitRootLogin yes)."))
        if configuration.get("passwordauthentication") == "yes":
            result.append(self.create_finding(SecurityFindingSeverity.Low, "ssh-server allows password-authentication (PasswordAuthentication yes)."))
        return result


class AuthorizedKeysCheck(SecurityCheckBase):
    """Authorized ssh-keys are the most common persistence-mechanism of attackers."""

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        minimal_uid = system.get_minimal_uid_of_regular_users()
        result: list[SecurityFinding] = []
        handled_home_folders: set[str] = set()
        for user in system.get_users():
            if user.home_folder in handled_home_folders or not user.home_folder.startswith("/"):
                continue
            handled_home_folders.add(user.home_folder)
            for file_name in ["authorized_keys", "authorized_keys2"]:
                file = f"{user.home_folder.rstrip('/')}/.ssh/{file_name}"
                content = system.read_text(file)
                if content is None:
                    continue
                keys = [line.strip() for line in content.splitlines() if line.strip() != "" and not line.strip().startswith("#")]
                if len(keys) == 0:
                    continue
                if file_name == "authorized_keys2":
                    result.append(self.create_finding(SecurityFindingSeverity.Mid, f"\"{file}\" contains {len(keys)} key(s). This deprecated file is rarely used legitimately and often overlooked."))
                if 0 < user.uid < minimal_uid:
                    result.append(self.create_finding(SecurityFindingSeverity.Mid, f"System-account \"{user.name}\" (uid {user.uid}) has {len(keys)} authorized ssh-key(s) in \"{file}\"."))
                for key in keys:
                    if "command=" in key.split(" ", 1)[0]:
                        result.append(self.create_finding(SecurityFindingSeverity.Low, f"Authorized ssh-key in \"{file}\" has a forced command: {key[:200]}"))
        return result
