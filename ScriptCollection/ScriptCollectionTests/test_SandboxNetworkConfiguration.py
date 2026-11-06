import unittest
from ..ScriptCollection.AgentSandboxNetwork.SandboxNetworkConfiguration import SandboxNetworkConfiguration, SandboxNetworkMode


class SandboxNetworkConfigurationTests(unittest.TestCase):

    def test_without_allowlist_the_network_access_is_unrestricted(self) -> None:
        # act
        configuration = SandboxNetworkConfiguration(None, None)

        # assert
        self.assertEqual(SandboxNetworkMode.Unrestricted, configuration.get_mode())
        self.assertIsNone(configuration.get_description())

    def test_empty_allowlist_blocks_the_network_access(self) -> None:
        # act
        configuration = SandboxNetworkConfiguration([], None)

        # assert
        self.assertEqual(SandboxNetworkMode.NoNetwork, configuration.get_mode())
        self.assertEqual("The sandbox has no network access.", configuration.get_description())

    def test_allowlist_with_domains_restricts_the_network_access(self) -> None:
        # act
        configuration = SandboxNetworkConfiguration(["api.example.com", ".example.org"], "example/squid:v1.0.0")

        # assert
        self.assertEqual(SandboxNetworkMode.Allowlist, configuration.get_mode())
        self.assertEqual("Network access of the sandbox is restricted to api.example.com, .example.org via HTTPS.", configuration.get_description())

    def test_entries_are_compared_case_insensitive(self) -> None:
        # act and assert
        self.assertEqual(["api.example.com"], SandboxNetworkConfiguration(["API.Example.com"], "example/squid:v1.0.0").allowed_domains)

    def test_egress_proxy_image_is_required_for_an_allowlist_with_domains(self) -> None:
        # act and assert
        with self.assertRaisesRegex(ValueError, "egress_proxy_image"):
            SandboxNetworkConfiguration(["example.com"], None)

    def test_invalid_entries_are_rejected_with_their_name(self) -> None:
        for entry in ["https://example.com", "example.com:443", "example.com/path", "*.example.com", "example", "-example.com", "exa_mple.com", "..example.com", "example..com", "", "1.2.3.4", "::1", "[::1]"]:
            with self.subTest(entry=entry):
                # act and assert
                with self.assertRaises(ValueError) as context:
                    SandboxNetworkConfiguration([entry], "example/squid:v1.0.0")
                self.assertIn(f"'{entry}'", str(context.exception))

    def test_valid_entries_are_accepted(self) -> None:
        # act and assert
        self.assertEqual(["example.com", ".example.org", "a-b.c1.example.net", "xn--bcher-kva.example"], SandboxNetworkConfiguration(["example.com", ".example.org", "a-b.c1.example.net", "xn--bcher-kva.example"], "example/squid:v1.0.0").allowed_domains)

    def test_entry_covered_by_an_entry_with_leading_dot_is_rejected(self) -> None:
        for entries, covered_entry, covering_entry in [
            ([".example.com", "api.example.com"], "api.example.com", ".example.com"),
            (["example.com", ".example.com"], "example.com", ".example.com"),
            ([".example.com", ".api.example.com"], ".api.example.com", ".example.com"),
            (["example.com", "example.com"], "example.com", "example.com"),
        ]:
            with self.subTest(entries=entries):
                # act and assert
                with self.assertRaisesRegex(ValueError, f"'{covered_entry}' is already covered by the allowlist-entry '{covering_entry}'"):
                    SandboxNetworkConfiguration(entries, "example/squid:v1.0.0")

    def test_entries_which_do_not_cover_each_other_are_accepted(self) -> None:
        # act and assert
        self.assertEqual(["example.com", "api.example.com", ".example.com.evil.org"], SandboxNetworkConfiguration(["example.com", "api.example.com", ".example.com.evil.org"], "example/squid:v1.0.0").allowed_domains)
