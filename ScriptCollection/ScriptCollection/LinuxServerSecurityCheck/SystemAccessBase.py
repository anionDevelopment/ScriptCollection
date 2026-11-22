import ipaddress
import os
import posixpath
import stat
import sys
from abc import ABC, abstractmethod
from collections.abc import Iterator
from .SystemEntities import UserAccount, ProcessInformation, ProgramResult, SocketInformation


class SystemAccessBase(ABC):
    """Read-only access to the system which is checked.
    All paths are absolute paths of the checked system.
    The abstract methods are the primitives which access the system; everything else is derived from them,
    so that a testcase only has to replace the primitives."""

    maximal_size_of_text_files: int = 50 * 1024 * 1024
    seconds_per_day: int = 24 * 60 * 60

    @abstractmethod
    def current_user_is_root(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def read_bytes(self, path: str, maximal_amount_of_bytes: int) -> bytes | None:
        """Returns the first bytes of the file or None if the file does not exist (anymore)."""
        raise NotImplementedError

    @abstractmethod
    def list_folder(self, path: str) -> list[str] | None:
        """Returns the names of the entries of the folder or None if the folder does not exist (anymore)."""
        raise NotImplementedError

    @abstractmethod
    def get_lstat(self, path: str) -> os.stat_result | None:
        """Returns the stat-information of the path itself (a symlink is not followed) or None if the path does not exist (anymore)."""
        raise NotImplementedError

    @abstractmethod
    def path_exists(self, path: str) -> bool:
        """Returns whether the path exists. Symlinks are followed."""
        raise NotImplementedError

    @abstractmethod
    def read_link(self, path: str) -> str | None:
        """Returns the target of the symlink or None if the symlink does not exist (anymore) or has no target (for example /proc/<pid>/exe of a kernel-thread)."""
        raise NotImplementedError

    @abstractmethod
    def program_is_available(self, program: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def run_program(self, program: str, arguments: list[str]) -> ProgramResult:
        """Runs a program which must not change anything on the system."""
        raise NotImplementedError

    @abstractmethod
    def get_file_attribute_flags(self, path: str) -> int | None:
        """Returns the inode-flags (as shown by lsattr) of a regular file or None if the filesystem does not support them."""
        raise NotImplementedError

    @abstractmethod
    def get_current_time(self) -> float:
        raise NotImplementedError

    def read_text(self, path: str) -> str | None:
        content = self.read_bytes(path, SystemAccessBase.maximal_size_of_text_files)
        if content is None:
            return None
        return content.decode("utf-8", errors="replace")

    def is_regular_file(self, path: str) -> bool:
        file_stat = self.get_lstat(path)
        return file_stat is not None and stat.S_ISREG(file_stat.st_mode)

    def is_symlink(self, path: str) -> bool:
        file_stat = self.get_lstat(path)
        return file_stat is not None and stat.S_ISLNK(file_stat.st_mode)

    def is_folder(self, path: str) -> bool:
        file_stat = self.get_lstat(path)
        return file_stat is not None and stat.S_ISDIR(file_stat.st_mode)

    def is_binary_content(self, content: bytes) -> bool:
        return b"\0" in content[:8192]

    def list_files_recursively(self, folder: str, excluded_folders: set[str]) -> Iterator[tuple[str, os.stat_result]]:
        """Yields every non-folder-entry (regular files, symlinks, ...) below the folder together with its lstat-information.
        Symlinks to folders are not followed. Folders contained in excluded_folders are not entered."""
        folders_to_visit: list[str] = [folder]
        while len(folders_to_visit) > 0:
            current_folder = folders_to_visit.pop()
            entries = self.list_folder(current_folder)
            if entries is None:
                continue
            for entry in sorted(entries):
                path = posixpath.join(current_folder, entry)
                entry_stat = self.get_lstat(path)
                if entry_stat is None:
                    continue
                if stat.S_ISDIR(entry_stat.st_mode):
                    if path not in excluded_folders:
                        folders_to_visit.append(path)
                else:
                    yield path, entry_stat

    def list_regular_files_recursively(self, folder: str) -> list[str]:
        return [path for path, file_stat in self.list_files_recursively(folder, set()) if stat.S_ISREG(file_stat.st_mode)]

    def path_is_alias(self, path: str) -> bool:
        """Returns whether the path is reachable only through a symlinked top-level-folder (for example /lib/systemd on a system with merged /usr),
        so that its content is already reachable through another path."""
        parts = [part for part in path.split("/") if part != ""]
        current = ""
        for part in parts[:-1]:
            current = current + "/" + part
            if self.is_symlink(current):
                return True
        return False

    def get_users(self) -> list[UserAccount]:
        content = self.read_text("/etc/passwd")
        if content is None:
            raise FileNotFoundError("/etc/passwd does not exist.")
        result: list[UserAccount] = []
        for line in content.splitlines():
            if line.strip() == "" or line.startswith("#"):
                continue
            fields = line.split(":")
            if len(fields) < 7:
                continue
            result.append(UserAccount(fields[0], int(fields[2]), int(fields[3]), fields[5], fields[6]))
        return result

    def get_home_folders(self) -> list[str]:
        result: list[str] = []
        for user in self.get_users():
            if user.home_folder not in result and user.home_folder.startswith("/") and self.is_folder(user.home_folder):
                result.append(user.home_folder)
        return result

    def get_minimal_uid_of_regular_users(self) -> int:
        content = self.read_text("/etc/login.defs")
        if content is not None:
            for line in content.splitlines():
                fields = line.split()
                if len(fields) == 2 and fields[0] == "UID_MIN":
                    return int(fields[1])
        # 1000 is the value which shadow-utils uses when UID_MIN is not defined in /etc/login.defs.
        return 1000

    def get_process_ids(self) -> list[int]:
        entries = self.list_folder("/proc")
        if entries is None:
            raise FileNotFoundError("/proc does not exist.")
        return sorted(int(entry) for entry in entries if entry.isdigit())

    def get_process(self, pid: int) -> ProcessInformation | None:
        """Returns None if the process does not exist (anymore)."""
        status = self.read_text(f"/proc/{pid}/status")
        if status is None:
            return None
        name = ""
        uid = -1
        for line in status.splitlines():
            if line.startswith("Name:"):
                name = line[len("Name:"):].strip()
            elif line.startswith("Uid:"):
                uid = int(line.split()[1])
        commandline_bytes = self.read_bytes(f"/proc/{pid}/cmdline", 65536)
        if commandline_bytes is None:
            return None
        commandline = commandline_bytes.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()
        executable = self.read_link(f"/proc/{pid}/exe")
        return ProcessInformation(pid, name, uid, executable, commandline)

    def get_processes(self) -> list[ProcessInformation]:
        result: list[ProcessInformation] = []
        for pid in self.get_process_ids():
            process = self.get_process(pid)
            if process is not None:
                result.append(process)
        return result

    def get_processes_by_socket_inode(self) -> dict[int, list[ProcessInformation]]:
        result: dict[int, list[ProcessInformation]] = {}
        for process in self.get_processes():
            file_descriptors = self.list_folder(f"/proc/{process.pid}/fd")
            if file_descriptors is None:
                continue
            for file_descriptor in file_descriptors:
                target = self.read_link(f"/proc/{process.pid}/fd/{file_descriptor}")
                if target is not None and target.startswith("socket:[") and target.endswith("]"):
                    inode = int(target[len("socket:["):-1])
                    processes = result.setdefault(inode, [])
                    if process not in processes:
                        processes.append(process)
        return result

    def get_sockets(self) -> list[SocketInformation]:
        """Returns the tcp- and udp-sockets of all network-namespaces (so also the sockets of containers)."""
        socket_tables: list[str] = []
        known_namespaces: set[str] = set()
        for pid in self.get_process_ids():
            namespace = self.read_link(f"/proc/{pid}/ns/net")
            if namespace is not None and namespace not in known_namespaces:
                known_namespaces.add(namespace)
                socket_tables.append(f"/proc/{pid}/net")
        if len(socket_tables) == 0:
            socket_tables.append("/proc/net")
        result: list[SocketInformation] = []
        known_inodes: set[int] = set()
        for socket_table in socket_tables:
            for protocol in ["tcp", "tcp6", "udp", "udp6"]:
                content = self.read_text(f"{socket_table}/{protocol}")
                if content is None:
                    continue
                for socket_information in SystemAccessBase.parse_socket_table(protocol, content):
                    if socket_information.inode == 0 or socket_information.inode not in known_inodes:
                        known_inodes.add(socket_information.inode)
                        result.append(socket_information)
        return result

    @staticmethod
    def parse_socket_table(protocol: str, content: str) -> list[SocketInformation]:
        result: list[SocketInformation] = []
        for line in content.splitlines()[1:]:
            fields = line.split()
            if len(fields) < 10:
                continue
            local_address, local_port = SystemAccessBase.decode_socket_address(fields[1])
            remote_address, remote_port = SystemAccessBase.decode_socket_address(fields[2])
            result.append(SocketInformation(protocol, local_address, local_port, remote_address, remote_port, fields[3].upper(), int(fields[9])))
        return result

    @staticmethod
    def decode_socket_address(hex_address: str) -> tuple[str, int]:
        """Decodes an address like "0100007F:0035" from /proc/net/tcp. The address consists of 32-bit-words in host-byte-order."""
        address_part, port_part = hex_address.split(":")
        raw_address = bytes.fromhex(address_part)
        if sys.byteorder == "little":
            raw_address = b"".join(raw_address[index:index + 4][::-1] for index in range(0, len(raw_address), 4))
        return str(ipaddress.ip_address(raw_address)), int(port_part, 16)
