import datetime
from ..SecurityCheckBase import SecurityCheckBase
from ..SecurityFinding import SecurityFinding, SecurityFindingSeverity
from ..SuspiciousCommandPatterns import SuspiciousCommandPatterns
from ..SystemAccessBase import SystemAccessBase


class AutostartLocations:
    """Files and folders which cause an automatic execution of commands (cron, systemd, shell-startup-files, ...)."""

    system_files: list[str] = ["/etc/crontab", "/etc/rc.local", "/etc/profile", "/etc/bash.bashrc", "/etc/bashrc", "/etc/environment", "/etc/zsh/zshrc", "/etc/ssh/sshrc"]
    system_folders: list[str] = ["/etc/cron.d", "/etc/cron.hourly", "/etc/cron.daily", "/etc/cron.weekly", "/etc/cron.monthly", "/var/spool/cron", "/etc/profile.d", "/etc/init.d", "/etc/update-motd.d", "/etc/udev/rules.d", "/etc/xdg/autostart",
                                 "/etc/systemd/system", "/etc/systemd/user", "/run/systemd/system", "/usr/lib/systemd/system", "/usr/lib/systemd/user", "/lib/systemd/system", "/lib/systemd/user", "/usr/local/lib/systemd/system"]
    user_files: list[str] = [".bashrc", ".bash_profile", ".bash_login", ".bash_logout", ".profile", ".zshrc", ".zprofile", ".ssh/rc"]
    user_folders: list[str] = [".config/autostart", ".config/systemd/user"]

    @staticmethod
    def get_files(system: SystemAccessBase) -> list[str]:
        files: list[str] = [file for file in AutostartLocations.system_files if system.is_regular_file(file)]
        folders: list[str] = list(AutostartLocations.system_folders)
        for home_folder in system.get_home_folders():
            files.extend(f"{home_folder.rstrip('/')}/{file}" for file in AutostartLocations.user_files if system.is_regular_file(f"{home_folder.rstrip('/')}/{file}"))
            folders.extend(f"{home_folder.rstrip('/')}/{folder}" for folder in AutostartLocations.user_folders)
        for folder in folders:
            if system.is_folder(folder) and not system.path_is_alias(folder):
                files.extend(system.list_regular_files_recursively(folder))
        return files


class SuspiciousCommandsInAutostartLocationsCheck(SecurityCheckBase):
    """Detects persistence-mechanisms (download-and-execute, reverse-shells, miners, ...) in cron-jobs, systemd-units, shell-startup-files and similar."""

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        result: list[SecurityFinding] = []
        for file in AutostartLocations.get_files(system):
            content = system.read_bytes(file, SystemAccessBase.maximal_size_of_text_files)
            if content is None or system.is_binary_content(content):
                continue
            for line_number, line in enumerate(content.decode("utf-8", errors="replace").splitlines(), start=1):
                if line.strip().startswith("#"):
                    continue
                for pattern in SuspiciousCommandPatterns.find_matches(line):
                    result.append(self.create_finding(pattern.severity, f"Suspicious command ({pattern.description}) in \"{file}\" line {line_number}: {line.strip()[:300]}"))
        return result


class LibraryPreloadConfigurationCheck(SecurityCheckBase):
    """/etc/ld.so.preload loads a library into every process. This is the typical installation-location of user-space-rootkits."""

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        content = system.read_text("/etc/ld.so.preload")
        if content is None:
            return []
        entries = [line.strip() for line in content.splitlines() if line.strip() != "" and not line.strip().startswith("#")]
        if len(entries) == 0:
            return []
        return [self.create_finding(SecurityFindingSeverity.High, f"/etc/ld.so.preload loads libraries into every process: {', '.join(entries)}")]


class CrontabsOfSystemAccountsCheck(SecurityCheckBase):
    """System-accounts (for example www-data after a compromised web-application) usually have no crontab."""

    __crontab_folders: list[str] = ["/var/spool/cron/crontabs", "/var/spool/cron"]

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        minimal_uid = system.get_minimal_uid_of_regular_users()
        system_accounts = {user.name: user.uid for user in system.get_users() if 0 < user.uid < minimal_uid}
        result: list[SecurityFinding] = []
        for folder in CrontabsOfSystemAccountsCheck.__crontab_folders:
            for entry in sorted(system.list_folder(folder) or []):
                file = f"{folder}/{entry}"
                if entry in system_accounts and system.is_regular_file(file):
                    result.append(self.create_finding(SecurityFindingSeverity.Mid, f"System-account \"{entry}\" (uid {system_accounts[entry]}) has a crontab: \"{file}\"."))
        return result


class RecentlyChangedSecurityRelevantFilesCheck(SecurityCheckBase):
    """Lists security-relevant files which were changed recently.
    The ctime is used instead of the mtime, because the mtime can be set arbitrarily (for example with "touch") while the ctime can not."""

    amount_of_days: int = 7
    files: list[str] = ["/etc/passwd", "/etc/shadow", "/etc/group", "/etc/gshadow", "/etc/sudoers", "/etc/crontab", "/etc/rc.local", "/etc/ld.so.preload", "/etc/ssh/sshd_config", "/etc/hosts", "/etc/resolv.conf"]
    folders: list[str] = ["/etc/sudoers.d", "/etc/cron.d", "/etc/cron.hourly", "/etc/cron.daily", "/etc/cron.weekly", "/etc/cron.monthly", "/var/spool/cron", "/etc/systemd/system", "/etc/profile.d", "/etc/ssh/sshd_config.d", "/etc/pam.d", "/etc/ld.so.conf.d"]

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        candidates: list[str] = list(RecentlyChangedSecurityRelevantFilesCheck.files)
        for folder in RecentlyChangedSecurityRelevantFilesCheck.folders:
            if system.is_folder(folder):
                candidates.extend(path for path, _ in system.list_files_recursively(folder, set()))
        for home_folder in system.get_home_folders():
            candidates.extend(f"{home_folder.rstrip('/')}/.ssh/{file}" for file in ["authorized_keys", "authorized_keys2"])
        minimal_ctime = system.get_current_time() - RecentlyChangedSecurityRelevantFilesCheck.amount_of_days * SystemAccessBase.seconds_per_day
        result: list[SecurityFinding] = []
        for path in candidates:
            file_stat = system.get_lstat(path)
            if file_stat is not None and file_stat.st_ctime >= minimal_ctime:
                moment = datetime.datetime.fromtimestamp(file_stat.st_ctime, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                result.append(self.create_finding(SecurityFindingSeverity.Low, f"\"{path}\" was changed within the last {RecentlyChangedSecurityRelevantFilesCheck.amount_of_days} days (at {moment})."))
        return result
