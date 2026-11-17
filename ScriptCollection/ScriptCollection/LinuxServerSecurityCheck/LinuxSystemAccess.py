import errno
import os
import shutil
import struct
import subprocess
import time
from .SystemAccessBase import SystemAccessBase
from .SystemEntities import ProgramResult


class LinuxSystemAccess(SystemAccessBase):
    """Accesses the local linux-system. Every method only reads, nothing is changed on the system."""

    # _IOR('f', 1, long) on 64-bit-systems.
    ioctl_get_flags: int = 0x80086601
    timeout_of_programs_in_seconds: int = 1800
    chunk_size: int = 65536

    def current_user_is_root(self) -> bool:
        return os.geteuid() == 0  # pylint:disable=no-member

    def read_bytes(self, path: str, maximal_amount_of_bytes: int) -> bytes | None:
        try:
            with open(path, "rb") as file:
                # read in chunks, because some files (for example in /proc/sys) refuse a single read with a large buffer.
                chunks: list[bytes] = []
                amount_of_read_bytes = 0
                while amount_of_read_bytes < maximal_amount_of_bytes:
                    chunk = file.read(min(LinuxSystemAccess.chunk_size, maximal_amount_of_bytes - amount_of_read_bytes))
                    if len(chunk) == 0:
                        break
                    chunks.append(chunk)
                    amount_of_read_bytes += len(chunk)
                return b"".join(chunks)
        except (FileNotFoundError, NotADirectoryError, ProcessLookupError):
            return None

    def list_folder(self, path: str) -> list[str] | None:
        try:
            return os.listdir(path)
        except (FileNotFoundError, NotADirectoryError, ProcessLookupError):
            return None

    def get_lstat(self, path: str) -> os.stat_result | None:
        try:
            return os.lstat(path)
        except (FileNotFoundError, NotADirectoryError, ProcessLookupError):
            return None

    def path_exists(self, path: str) -> bool:
        return os.path.exists(path)

    def read_link(self, path: str) -> str | None:
        try:
            return os.readlink(path)
        except (FileNotFoundError, NotADirectoryError, ProcessLookupError):
            return None

    def program_is_available(self, program: str) -> bool:
        return shutil.which(program) is not None

    def run_program(self, program: str, arguments: list[str]) -> ProgramResult:
        environment = dict(os.environ)
        environment["LC_ALL"] = "C"
        completed_process = subprocess.run([program] + arguments, stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace", env=environment, timeout=LinuxSystemAccess.timeout_of_programs_in_seconds, check=False)
        return ProgramResult(completed_process.returncode, completed_process.stdout, completed_process.stderr)

    def get_file_attribute_flags(self, path: str) -> int | None:
        import fcntl  # pylint:disable=import-outside-toplevel,import-error  # fcntl only exists on unix-systems
        try:
            file_descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)  # pylint:disable=no-member
        except FileNotFoundError:
            return None
        try:
            buffer = fcntl.ioctl(file_descriptor, LinuxSystemAccess.ioctl_get_flags, b"\0" * 8)  # pylint:disable=no-member
            return struct.unpack("i", buffer[:4])[0]
        except OSError as error:
            if error.errno in (errno.ENOTTY, errno.EOPNOTSUPP, errno.EINVAL, errno.ENOSYS):
                return None
            raise
        finally:
            os.close(file_descriptor)

    def get_current_time(self) -> float:
        return time.time()
