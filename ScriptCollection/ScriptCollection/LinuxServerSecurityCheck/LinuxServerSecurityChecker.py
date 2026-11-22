import time
from ..SCLog import SCLog, LogLevel
from .SecurityCheckBase import SecurityCheckBase
from .SecurityFinding import SecurityFinding, SecurityFindingSeverity
from .SystemAccessBase import SystemAccessBase
from .Checks.AccountChecks import NonRootAccountsWithUid0Check, AccountsWithoutPasswordCheck, DuplicateUidsCheck, SystemAccountsWithLoginShellCheck, SudoersWithoutPasswordCheck
from .Checks.SSHChecks import SshServerConfigurationCheck, AuthorizedKeysCheck
from .Checks.ProcessChecks import ProcessesRunningFromTemporaryFoldersCheck, ProcessesWithDeletedExecutableCheck, ProcessesMasqueradingAsKernelThreadsCheck, SuspiciousProcessCommandlinesCheck, ProcessesWithPreloadedLibrariesCheck
from .Checks.NetworkChecks import PromiscuousNetworkInterfacesCheck, SuspiciousListeningPortsCheck, ConnectionsToMiningPoolPortsCheck
from .Checks.PersistenceChecks import SuspiciousCommandsInAutostartLocationsCheck, LibraryPreloadConfigurationCheck, CrontabsOfSystemAccountsCheck, RecentlyChangedSecurityRelevantFilesCheck
from .Checks.FileSystemChecks import SetuidFilesCheck, SuspiciousFilesInTemporaryFoldersCheck, CriticalFilePermissionsCheck, ImmutableFilesCheck
from .Checks.KernelChecks import UnknownKernelModulesCheck, KernelTaintCheck
from .Checks.PackageIntegrityChecks import ModifiedPackageFilesCheck, UnpackagedPamModulesCheck
from .Checks.ContainerChecks import PrivilegedDockerContainersCheck
from .Checks.LogChecks import RedirectedShellHistoriesCheck, EmptyLoginRecordsCheck


class LinuxServerSecurityChecker:
    """Runs read-only checks on a linux-server to detect signs of a compromise or of suspicious activities.
    Every finding is logged as one line with the prefix "[High]", "[Mid]" or "[Low]".
    The exitcode is the amount of high-findings (capped at maximal_exit_code_for_findings) or exit_code_for_application_error if a check could not be executed."""

    maximal_exit_code_for_findings: int = 254
    exit_code_for_application_error: int = 255

    def __init__(self, log: SCLog, system: SystemAccessBase, checks: list[SecurityCheckBase]):
        self.__log = log
        self.__system = system
        self.__checks = checks

    @staticmethod
    def get_default_checks() -> list[SecurityCheckBase]:
        return [
            NonRootAccountsWithUid0Check(),
            AccountsWithoutPasswordCheck(),
            DuplicateUidsCheck(),
            SystemAccountsWithLoginShellCheck(),
            SudoersWithoutPasswordCheck(),
            SshServerConfigurationCheck(),
            AuthorizedKeysCheck(),
            ProcessesRunningFromTemporaryFoldersCheck(),
            ProcessesWithDeletedExecutableCheck(),
            ProcessesMasqueradingAsKernelThreadsCheck(),
            SuspiciousProcessCommandlinesCheck(),
            ProcessesWithPreloadedLibrariesCheck(),
            PromiscuousNetworkInterfacesCheck(),
            SuspiciousListeningPortsCheck(),
            ConnectionsToMiningPoolPortsCheck(),
            SuspiciousCommandsInAutostartLocationsCheck(),
            LibraryPreloadConfigurationCheck(),
            CrontabsOfSystemAccountsCheck(),
            RecentlyChangedSecurityRelevantFilesCheck(),
            SetuidFilesCheck(),
            SuspiciousFilesInTemporaryFoldersCheck(),
            CriticalFilePermissionsCheck(),
            ImmutableFilesCheck(),
            UnknownKernelModulesCheck(),
            KernelTaintCheck(),
            ModifiedPackageFilesCheck(),
            UnpackagedPamModulesCheck(),
            PrivilegedDockerContainersCheck(),
            RedirectedShellHistoriesCheck(),
            EmptyLoginRecordsCheck(),
        ]

    def run(self) -> int:
        if not self.__system.current_user_is_root():
            raise PermissionError("The security-check must be executed as root.")
        findings: list[SecurityFinding] = []
        failed_checks: list[str] = []
        for check in self.__checks:
            start = time.monotonic()
            self.__log.log(f"Run check \"{check.get_name()}\".", LogLevel.Debug)
            try:
                check_findings = check.run(self.__system)
            except Exception as exception:  # pylint:disable=broad-exception-caught
                # the other checks are still executed, because one failing check must not hide the findings of the other checks.
                self.__log.log_exception(f"Check \"{check.get_name()}\" failed.", exception, LogLevel.Error)
                failed_checks.append(check.get_name())
                continue
            for finding in check_findings:
                self.__log.log(finding.to_line(), LogLevel.Information)
            findings.extend(check_findings)
            self.__log.log(f"Check \"{check.get_name()}\" finished in {time.monotonic() - start:.1f} seconds with {len(check_findings)} finding(s).", LogLevel.Debug)
        amount_of_high_findings = len([finding for finding in findings if finding.severity == SecurityFindingSeverity.High])
        self.__log.log(f"Summary: {len(findings)} finding(s), {amount_of_high_findings} with severity high, {len(failed_checks)} failed check(s).", LogLevel.Debug)
        if len(failed_checks) > 0:
            self.__log.log(f"The following checks failed: {', '.join(failed_checks)}", LogLevel.Error)
            return LinuxServerSecurityChecker.exit_code_for_application_error
        return min(amount_of_high_findings, LinuxServerSecurityChecker.maximal_exit_code_for_findings)
