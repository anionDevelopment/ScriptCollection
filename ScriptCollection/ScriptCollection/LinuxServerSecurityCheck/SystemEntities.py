from dataclasses import dataclass


@dataclass(frozen=True)
class UserAccount:
    name: str
    uid: int
    gid: int
    home_folder: str
    shell: str


@dataclass(frozen=True)
class ProcessInformation:
    pid: int
    name: str
    uid: int
    executable: str | None
    """Target of /proc/<pid>/exe as seen from the mount-namespace of the process. None for kernel-threads and zombies."""
    commandline: str

    def is_kernel_thread_or_zombie(self) -> bool:
        return self.executable is None and self.commandline == ""

    def describe(self) -> str:
        return f"pid {self.pid} (name \"{self.name}\", uid {self.uid}, executable \"{self.executable}\", commandline \"{self.commandline[:300]}\")"


@dataclass(frozen=True)
class ProgramResult:
    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class SocketInformation:
    protocol: str
    local_address: str
    local_port: int
    remote_address: str
    remote_port: int
    state: str
    """Hex-state as written in /proc/net/tcp, for example "0A" for listening tcp-sockets."""
    inode: int
