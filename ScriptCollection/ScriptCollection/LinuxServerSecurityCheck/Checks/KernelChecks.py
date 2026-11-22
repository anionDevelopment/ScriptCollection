from ..SecurityCheckBase import SecurityCheckBase
from ..SecurityFinding import SecurityFinding, SecurityFindingSeverity
from ..SystemAccessBase import SystemAccessBase


class UnknownKernelModulesCheck(SecurityCheckBase):
    """A loaded kernel-module which is not part of the module-tree of the running kernel was loaded manually from somewhere else (for example by a rootkit via insmod)."""

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        loaded_modules = system.read_text("/proc/modules")
        if loaded_modules is None:
            return []  # kernel without support for loadable modules
        kernel_release = system.read_text("/proc/sys/kernel/osrelease")
        if kernel_release is None:
            raise FileNotFoundError("/proc/sys/kernel/osrelease does not exist.")
        modules_dep_file = f"/lib/modules/{kernel_release.strip()}/modules.dep"
        modules_dep = system.read_text(modules_dep_file)
        loaded_module_names = [line.split()[0] for line in loaded_modules.splitlines() if line.strip() != ""]
        if modules_dep is None:
            if len(loaded_module_names) == 0:
                return []
            return [self.create_finding(SecurityFindingSeverity.Low, f"Loaded kernel-modules can not be verified because \"{modules_dep_file}\" does not exist.")]
        known_module_names: set[str] = set()
        for line in modules_dep.splitlines():
            module_path = line.split(":", 1)[0].strip()
            if module_path != "":
                known_module_names.add(UnknownKernelModulesCheck.__normalize(module_path.rsplit("/", 1)[-1].split(".", 1)[0]))
        return [self.create_finding(SecurityFindingSeverity.Mid, f"Loaded kernel-module \"{name}\" is not part of the module-tree of the running kernel ({modules_dep_file}).")
                for name in loaded_module_names if UnknownKernelModulesCheck.__normalize(name) not in known_module_names]

    @staticmethod
    def __normalize(module_name: str) -> str:
        return module_name.replace("-", "_")


class KernelTaintCheck(SecurityCheckBase):
    """The kernel is tainted when proprietary, out-of-tree or unsigned modules were loaded, which is also the case for many rootkits."""

    __relevant_flags: dict[int, str] = {0: "proprietary module was loaded", 12: "out-of-tree module was loaded", 13: "unsigned module was loaded"}

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        content = system.read_text("/proc/sys/kernel/tainted")
        if content is None:
            return []
        taint = int(content.strip())
        reasons = [description for bit, description in KernelTaintCheck.__relevant_flags.items() if taint & (1 << bit) != 0]
        if len(reasons) == 0:
            return []
        return [self.create_finding(SecurityFindingSeverity.Low, f"Kernel is tainted (value {taint}): {', '.join(reasons)}.")]
