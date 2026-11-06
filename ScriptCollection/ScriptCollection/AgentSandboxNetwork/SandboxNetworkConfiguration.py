import ipaddress
import re
from enum import Enum
from ..GeneralUtilities import GeneralUtilities


class SandboxNetworkMode(Enum):
    Unrestricted = "unrestricted"
    Allowlist = "allowlist"
    NoNetwork = "none"


class SandboxNetworkConfiguration:
    """The network-access of the agent-sandbox. Without allowlist (allowed_domains is None) the network-access is unrestricted. With an allowlist
    everything except the listed domains is blocked: an allowlist with domains allows only these domains via HTTPS (enforced by an egress-proxy),
    an allowlist without domain blocks the network-access completely.
    An entry without leading dot allows exactly this host, an entry with leading dot allows the domain and all of its subdomains."""
    __label_pattern = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
    allowed_domains: list[str] = None
    egress_proxy_image: str = None

    @GeneralUtilities.check_arguments
    def __init__(self, allowed_domains: list[str], egress_proxy_image: str):
        # allowed_domains is None if no allowlist is defined. egress_proxy_image is only required if the allowlist contains at least one domain.
        # Invalid configurations are rejected here, so nothing is started for them.
        if allowed_domains is not None:
            allowed_domains = [allowed_domain.lower() for allowed_domain in allowed_domains]
            for allowed_domain in allowed_domains:
                SandboxNetworkConfiguration.__assert_entry_is_valid(allowed_domain)
            SandboxNetworkConfiguration.__assert_no_entry_is_redundant(allowed_domains)
        self.allowed_domains = allowed_domains
        self.egress_proxy_image = egress_proxy_image
        if self.get_mode() == SandboxNetworkMode.Allowlist:
            GeneralUtilities.assert_condition(egress_proxy_image is not None, "The value 'egress_proxy_image' is required because the allowlist (section 'AllowedDomains' or argument '--alloweddomain') contains at least one domain, but it is neither given as argument nor defined in the configuration-file.")

    @GeneralUtilities.check_arguments
    def get_mode(self) -> SandboxNetworkMode:
        if self.allowed_domains is None:
            return SandboxNetworkMode.Unrestricted
        if len(self.allowed_domains) == 0:
            return SandboxNetworkMode.NoNetwork
        return SandboxNetworkMode.Allowlist

    @GeneralUtilities.check_arguments
    def get_description(self) -> str:
        # The description of the restriction which is shown at start. It is None for the unrestricted network-access, so the output stays as before.
        mode = self.get_mode()
        if mode == SandboxNetworkMode.NoNetwork:
            return "The sandbox has no network access."
        if mode == SandboxNetworkMode.Allowlist:
            return f"Network access of the sandbox is restricted to {', '.join(self.allowed_domains)} via HTTPS."
        return None

    @staticmethod
    @GeneralUtilities.check_arguments
    def __assert_entry_is_valid(entry: str) -> None:
        host = entry.removeprefix(".")
        invalid_entry_message = f"The allowlist-entry '{entry}' is invalid. Expected a hostname like 'example.com' (exactly this host) or '.example.com' (the domain and all of its subdomains) without scheme, port, path or wildcard."
        GeneralUtilities.assert_condition(not SandboxNetworkConfiguration.__is_ip_address(host), f"The allowlist-entry '{entry}' is an IP-address, but only hostnames are allowed.")
        labels = host.split(".")
        GeneralUtilities.assert_condition(len(host) <= 253 and len(labels) >= 2, invalid_entry_message)
        for label in labels:
            GeneralUtilities.assert_condition(SandboxNetworkConfiguration.__label_pattern.match(label) is not None, invalid_entry_message)

    @staticmethod
    @GeneralUtilities.check_arguments
    def __is_ip_address(host: str) -> bool:
        try:
            ipaddress.ip_address(host.strip("[]"))
            return True
        except ValueError:
            return False

    @staticmethod
    @GeneralUtilities.check_arguments
    def __assert_no_entry_is_redundant(allowed_domains: list[str]) -> None:
        # A redundant entry is rejected because it shows a misunderstanding of the matching (and the egress-proxy would complain about overlapping entries).
        for index, entry in enumerate(allowed_domains):
            for other_index, other_entry in enumerate(allowed_domains):
                if index == other_index:
                    continue
                if entry == other_entry and other_index > index:
                    # A duplicate is reported only once (at its second occurrence).
                    continue
                if SandboxNetworkConfiguration.__covers(other_entry, entry):
                    raise ValueError(f"The allowlist-entry '{entry}' is already covered by the allowlist-entry '{other_entry}'.")

    @staticmethod
    @GeneralUtilities.check_arguments
    def __covers(covering_entry: str, covered_entry: str) -> bool:
        # Returns whether everything which is allowed by covered_entry is also allowed by covering_entry.
        if covering_entry.startswith("."):
            covered_host = covered_entry.removeprefix(".")
            return covered_host == covering_entry[1:] or covered_host.endswith(covering_entry)
        return covering_entry == covered_entry
