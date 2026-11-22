from .SystemAccessBase import SystemAccessBase


class PackageOwnershipLookup:
    """Determines whether a file is owned by a package of the package-manager (dpkg or rpm)."""

    __merged_usr_prefixes: tuple[str, ...] = ("/usr/bin/", "/usr/sbin/", "/usr/lib/", "/usr/lib32/", "/usr/lib64/", "/usr/libx32/")

    def __init__(self, system: SystemAccessBase):
        self.__system = system
        self.__dpkg_files: set[str] | None = None

    def is_available(self) -> bool:
        return self.__uses_dpkg() or self.__system.program_is_available("rpm")

    def is_owned_by_package(self, path: str) -> bool:
        if self.__uses_dpkg():
            return PackageOwnershipLookup.__canonicalize(path) in self.__get_dpkg_files()
        if self.__system.program_is_available("rpm"):
            return self.__system.run_program("rpm", ["-qf", path]).exit_code == 0
        raise ValueError("No supported package-manager available.")

    def __uses_dpkg(self) -> bool:
        return self.__system.is_folder("/var/lib/dpkg/info")

    def __get_dpkg_files(self) -> set[str]:
        if self.__dpkg_files is None:
            files: set[str] = set()
            for entry in self.__system.list_folder("/var/lib/dpkg/info") or []:
                if entry.endswith(".list"):
                    content = self.__system.read_text(f"/var/lib/dpkg/info/{entry}")
                    if content is not None:
                        files.update(PackageOwnershipLookup.__canonicalize(line.strip()) for line in content.splitlines() if line.strip() != "")
            self.__dpkg_files = files
        return self.__dpkg_files

    @staticmethod
    def __canonicalize(path: str) -> str:
        """Maps "/usr/bin/x" and "/bin/x" to the same value, because on systems with merged /usr both refer to the same file and dpkg may know only one of them."""
        if path.startswith(PackageOwnershipLookup.__merged_usr_prefixes):
            return path[len("/usr"):]
        return path
