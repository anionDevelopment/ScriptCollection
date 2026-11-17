import re
import stat
from ..PackageOwnershipLookup import PackageOwnershipLookup
from ..SecurityCheckBase import SecurityCheckBase
from ..SecurityFinding import SecurityFinding, SecurityFindingSeverity
from ..SuspiciousCommandPatterns import SuspiciousCommandPatterns
from ..SystemAccessBase import SystemAccessBase


class SetuidFilesCheck(SecurityCheckBase):
    """Setuid-/setgid-files allow privilege-escalation. Attackers place them (for example a copy of a shell) as backdoor.
    The whole filesystem is searched except pseudo-filesystems, network-filesystems and the storage of container-runtimes
    (whose images legitimately contain setuid-files like "su")."""

    excluded_folders: set[str] = {"/proc", "/sys", "/dev", "/var/lib/docker", "/var/lib/containerd", "/var/lib/containers", "/var/lib/lxc", "/var/lib/lxd", "/snap", "/var/snap", "/var/lib/snapd"}
    included_folders_below_excluded_folders: list[str] = ["/dev/shm"]
    excluded_filesystem_types: set[str] = {"proc", "sysfs", "devtmpfs", "devpts", "cgroup", "cgroup2", "securityfs", "debugfs", "tracefs", "pstore", "bpf", "configfs", "fusectl", "mqueue", "hugetlbfs", "autofs", "binfmt_misc", "nsfs", "overlay", "squashfs", "efivarfs", "rpc_pipefs",
                                           "nfs", "nfs4", "cifs", "smb3", "smbfs", "sshfs", "9p", "ceph", "glusterfs"}
    standard_folders: tuple[str, ...] = ("/usr/bin/", "/usr/sbin/", "/bin/", "/sbin/", "/usr/lib/", "/usr/lib32/", "/usr/lib64/", "/usr/libexec/", "/lib/", "/lib32/", "/lib64/")
    manually_installed_software_folders: tuple[str, ...] = ("/usr/local/", "/opt/")

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        package_ownership = PackageOwnershipLookup(system)
        result: list[SecurityFinding] = []
        excluded_folders = self.__get_excluded_folders(system)
        for start_folder in ["/"] + SetuidFilesCheck.included_folders_below_excluded_folders:
            for path, file_stat in system.list_files_recursively(start_folder, excluded_folders):
                if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_mode & (stat.S_ISUID | stat.S_ISGID) == 0:
                    continue
                kind = "setuid" if file_stat.st_mode & stat.S_ISUID != 0 else "setgid"
                description = f"{kind}-file \"{path}\" (owner-uid {file_stat.st_uid}, mode {oct(stat.S_IMODE(file_stat.st_mode))})"
                if SuspiciousCommandPatterns.is_in_temporary_folder(path) or SuspiciousCommandPatterns.contains_hidden_path_component(path):
                    result.append(self.create_finding(SecurityFindingSeverity.High, f"{description} in a temporary or hidden folder."))
                elif path.startswith(SetuidFilesCheck.standard_folders):
                    if package_ownership.is_available() and not package_ownership.is_owned_by_package(path):
                        result.append(self.create_finding(SecurityFindingSeverity.High, f"{description} is not owned by any installed package."))
                elif path.startswith(SetuidFilesCheck.manually_installed_software_folders):
                    result.append(self.create_finding(SecurityFindingSeverity.Low, f"{description} in a folder for manually installed software."))
                else:
                    result.append(self.create_finding(SecurityFindingSeverity.Mid, f"{description} in an unusual location."))
        return result

    def __get_excluded_folders(self, system: SystemAccessBase) -> set[str]:
        result = set(SetuidFilesCheck.excluded_folders)
        mounts = system.read_text("/proc/mounts")
        if mounts is None:
            raise FileNotFoundError("/proc/mounts does not exist.")
        for line in mounts.splitlines():
            fields = line.split()
            if len(fields) >= 3 and (fields[2] in SetuidFilesCheck.excluded_filesystem_types or fields[2].startswith("fuse.")):
                # /proc/mounts escapes whitespaces as octal-sequences (for example "\040").
                result.add(re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), fields[1]))
        result.discard("/")
        return result


class SuspiciousFilesInTemporaryFoldersCheck(SecurityCheckBase):
    """Attackers drop their tools into world-writable temporary folders, often hidden (name starting with ".") or with misleading names like "..." ."""

    temporary_folders: list[str] = ["/tmp", "/var/tmp", "/dev/shm"]
    usual_hidden_entries: set[str] = {".X11-unix", ".ICE-unix", ".font-unix", ".XIM-unix", ".Test-unix"}
    __usual_hidden_entry_pattern = re.compile(r"^(\.X[0-9]+-lock|\.veracrypt_aux_mnt[0-9]+)$")
    __misleading_name_pattern = re.compile(r"^[.\s]+$")
    __elf_magic: bytes = b"\x7fELF"

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        result: list[SecurityFinding] = []
        for temporary_folder in SuspiciousFilesInTemporaryFoldersCheck.temporary_folders:
            for entry in sorted(system.list_folder(temporary_folder) or []):
                if SuspiciousFilesInTemporaryFoldersCheck.__misleading_name_pattern.match(entry):
                    result.append(self.create_finding(SecurityFindingSeverity.High, f"Entry with misleading name \"{temporary_folder}/{entry}\" (only dots and whitespaces)."))
                elif entry.startswith(".") and entry not in SuspiciousFilesInTemporaryFoldersCheck.usual_hidden_entries and not SuspiciousFilesInTemporaryFoldersCheck.__usual_hidden_entry_pattern.match(entry):
                    result.append(self.create_finding(SecurityFindingSeverity.Mid, f"Hidden entry \"{temporary_folder}/{entry}\" in a temporary folder."))
            for path, file_stat in system.list_files_recursively(temporary_folder, set()):
                if not stat.S_ISREG(file_stat.st_mode):
                    continue
                header = system.read_bytes(path, 4)
                if header == SuspiciousFilesInTemporaryFoldersCheck.__elf_magic:
                    severity = SecurityFindingSeverity.High if SuspiciousCommandPatterns.contains_hidden_path_component(path) else SecurityFindingSeverity.Mid
                    result.append(self.create_finding(severity, f"Executable binary (ELF) \"{path}\" (owner-uid {file_stat.st_uid}, size {file_stat.st_size} bytes) in a temporary folder."))
        return result


class CriticalFilePermissionsCheck(SecurityCheckBase):
    """Wrong permissions of critical files allow privilege-escalation or reading of password-hashes."""

    files_which_must_not_be_world_writable: list[str] = ["/etc/passwd", "/etc/group", "/etc/sudoers", "/etc/crontab", "/etc/ld.so.preload", "/etc/rc.local", "/etc/profile", "/etc/bash.bashrc", "/etc/environment", "/etc/ssh/sshd_config"]
    folders_whose_files_must_not_be_world_writable: list[str] = ["/etc/sudoers.d", "/etc/cron.d", "/etc/cron.hourly", "/etc/cron.daily", "/etc/cron.weekly", "/etc/cron.monthly", "/etc/systemd/system", "/etc/profile.d", "/etc/pam.d", "/etc/ssh/sshd_config.d", "/root"]
    files_which_must_not_be_world_readable: list[str] = ["/etc/shadow", "/etc/gshadow"]

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        result: list[SecurityFinding] = []
        world_writable_candidates: list[str] = list(CriticalFilePermissionsCheck.files_which_must_not_be_world_writable)
        for folder in CriticalFilePermissionsCheck.folders_whose_files_must_not_be_world_writable:
            if system.is_folder(folder):
                world_writable_candidates.append(folder)
                world_writable_candidates.extend(system.list_regular_files_recursively(folder))
        for home_folder in system.get_home_folders():
            world_writable_candidates.extend(f"{home_folder.rstrip('/')}/.ssh/{file}" for file in ["authorized_keys", "authorized_keys2"])
        for path in world_writable_candidates:
            file_stat = system.get_lstat(path)
            if file_stat is None or stat.S_ISLNK(file_stat.st_mode):
                continue
            if stat.S_ISDIR(file_stat.st_mode) and file_stat.st_mode & stat.S_ISVTX != 0:
                continue
            if file_stat.st_mode & stat.S_IWOTH != 0:
                result.append(self.create_finding(SecurityFindingSeverity.High, f"\"{path}\" is writable for everybody (mode {oct(stat.S_IMODE(file_stat.st_mode))})."))
        for path in CriticalFilePermissionsCheck.files_which_must_not_be_world_readable:
            file_stat = system.get_lstat(path)
            if file_stat is not None and file_stat.st_mode & (stat.S_IROTH | stat.S_IWOTH) != 0:
                result.append(self.create_finding(SecurityFindingSeverity.High, f"\"{path}\" is readable or writable for everybody (mode {oct(stat.S_IMODE(file_stat.st_mode))})."))
        return result


class ImmutableFilesCheck(SecurityCheckBase):
    """Attackers make their persistence-files immutable (chattr +i) so that they can not be removed easily."""

    __flag_immutable: int = 0x10
    __flag_append_only: int = 0x20
    files: list[str] = ["/etc/passwd", "/etc/shadow", "/etc/group", "/etc/sudoers", "/etc/crontab", "/etc/ld.so.preload", "/etc/rc.local", "/etc/hosts", "/etc/resolv.conf", "/etc/ssh/sshd_config"]
    folders: list[str] = ["/etc/cron.d", "/var/spool/cron", "/etc/sudoers.d", "/etc/systemd/system", "/etc/profile.d"]

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        candidates: list[str] = list(ImmutableFilesCheck.files)
        for folder in ImmutableFilesCheck.folders:
            if system.is_folder(folder):
                candidates.extend(system.list_regular_files_recursively(folder))
        for home_folder in system.get_home_folders():
            candidates.extend(f"{home_folder.rstrip('/')}/.ssh/{file}" for file in ["authorized_keys", "authorized_keys2"])
        result: list[SecurityFinding] = []
        for path in candidates:
            if not system.is_regular_file(path):
                continue
            flags = system.get_file_attribute_flags(path)
            if flags is None:
                continue
            if flags & ImmutableFilesCheck.__flag_immutable != 0:
                result.append(self.create_finding(SecurityFindingSeverity.Mid, f"\"{path}\" is immutable (chattr +i)."))
            if flags & ImmutableFilesCheck.__flag_append_only != 0:
                result.append(self.create_finding(SecurityFindingSeverity.Mid, f"\"{path}\" is append-only (chattr +a)."))
        return result
