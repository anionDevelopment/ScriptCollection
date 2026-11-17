from ..PackageOwnershipLookup import PackageOwnershipLookup
from ..SecurityCheckBase import SecurityCheckBase
from ..SecurityFinding import SecurityFinding, SecurityFindingSeverity
from ..SystemAccessBase import SystemAccessBase


class ModifiedPackageFilesCheck(SecurityCheckBase):
    """Compares the checksums of the installed files with the checksums of the package-manager.
    Rootkits often replace programs like ps, ls, netstat or ssh, or PAM-modules."""

    executable_folders: tuple[str, ...] = ("/usr/bin/", "/usr/sbin/", "/bin/", "/sbin/")
    library_folders: tuple[str, ...] = ("/usr/lib/", "/usr/lib32/", "/usr/lib64/", "/usr/libexec/", "/lib/", "/lib32/", "/lib64/")

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        if system.program_is_available("dpkg"):
            program_result = system.run_program("dpkg", ["--verify"])
        elif system.program_is_available("rpm"):
            program_result = system.run_program("rpm", ["-Va", "--nomtime"])
        else:
            return []
        result: list[SecurityFinding] = []
        for line in program_result.stdout.splitlines():
            fields = line.split()
            if len(fields) < 2 or len(fields[0]) < 9:
                continue
            flags = fields[0]
            is_configuration_file = len(fields) >= 3 and fields[1] == "c"
            path = fields[-1]
            if flags[2] != "5" or is_configuration_file:
                continue
            if path.startswith(ModifiedPackageFilesCheck.executable_folders) or "/security/pam_" in path:
                result.append(self.create_finding(SecurityFindingSeverity.High, f"Content of \"{path}\" differs from the installed package (verification-flags \"{flags}\")."))
            elif path.startswith(ModifiedPackageFilesCheck.library_folders):
                result.append(self.create_finding(SecurityFindingSeverity.Mid, f"Content of \"{path}\" differs from the installed package (verification-flags \"{flags}\")."))
        return result


class UnpackagedPamModulesCheck(SecurityCheckBase):
    """A PAM-module which does not belong to a package can capture passwords or allow logins with a master-password."""

    library_folders: list[str] = ["/usr/lib", "/usr/lib64", "/lib", "/lib64"]

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        package_ownership = PackageOwnershipLookup(system)
        if not package_ownership.is_available():
            return []
        result: list[SecurityFinding] = []
        for folder in self.__get_pam_module_folders(system):
            for entry in sorted(system.list_folder(folder) or []):
                path = f"{folder}/{entry}"
                if entry.endswith(".so") and system.is_regular_file(path) and not package_ownership.is_owned_by_package(path):
                    result.append(self.create_finding(SecurityFindingSeverity.High, f"PAM-module \"{path}\" is not owned by any installed package."))
        return result

    def __get_pam_module_folders(self, system: SystemAccessBase) -> list[str]:
        result: list[str] = []
        for library_folder in UnpackagedPamModulesCheck.library_folders:
            if not system.is_folder(library_folder) or system.path_is_alias(f"{library_folder}/security"):
                continue
            candidates = [f"{library_folder}/security"] + [f"{library_folder}/{entry}/security" for entry in sorted(system.list_folder(library_folder) or [])]
            result.extend(candidate for candidate in candidates if system.is_folder(candidate))
        return result
