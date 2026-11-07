import os
import subprocess
import unittest
from unittest import mock
from ..ScriptCollection.AgentSandboxNetwork import SandboxEgressProxy as SandboxEgressProxyModule
from ..ScriptCollection.AgentSandboxNetwork.SandboxEgressProxy import SandboxEgressProxy


class SandboxEgressProxyTests(unittest.TestCase):

    def __run(self, failing_subcommand: str = None, verbose: bool = False, logs: str = "", docker_commands: list[list[str]] = None) -> tuple[list[list[str]], list[str], list[str]]:
        # Starts and stops an egress-proxy with replaced docker. Returns the docker-commands (also recorded in docker_commands if given), the
        # configuration-files which existed during the run and the messages.
        if docker_commands is None:
            docker_commands = []
        configuration_files: list[str] = []
        messages: list[str] = []

        def run(command, **_):
            docker_commands.append(command)
            for argument in command:
                if argument.endswith(":/etc/squid/squid.conf:ro"):
                    configuration_files.append(argument.removesuffix(":/etc/squid/squid.conf:ro"))
            if failing_subcommand is not None and " ".join(command[1:]).startswith(failing_subcommand + " "):
                return subprocess.CompletedProcess(command, 1, "", "failed")
            return subprocess.CompletedProcess(command, 0, logs if command[1] == "exec" else "", "")
        egress_proxy = SandboxEgressProxy(["api.example.com"], "example/squid:v1.0.0", verbose)
        with mock.patch("subprocess.run", side_effect=run), mock.patch.object(SandboxEgressProxyModule.GeneralUtilities, "write_message_to_stderr", side_effect=messages.append):
            try:
                egress_proxy.start()
            finally:
                egress_proxy.stop()
        return docker_commands, configuration_files, messages

    def test_squid_configuration_only_allows_https_to_the_allowed_domains(self) -> None:
        # act
        configuration = SandboxEgressProxy.get_squid_configuration(["api.example.com", ".example.org"])

        # assert
        self.assertEqual("\n".join([
            "http_port 3128",
            "acl allowed_domains dstdomain -n api.example.com .example.org",
            "acl https_port port 443",
            "http_access deny !CONNECT",
            "http_access deny CONNECT !https_port",
            "http_access allow CONNECT allowed_domains",
            "http_access deny all",
            "cache deny all",
            "access_log stdio:/var/log/squid/access.log",
            "buffered_logs off",
            "pinger_enable off",
        ]) + "\n", configuration)

    def test_proxy_is_only_reachable_through_the_internal_network_and_everything_is_removed(self) -> None:
        # act
        docker_commands, configuration_files, _ = self.__run()

        # assert
        network_name = docker_commands[0][-1]
        proxy_name = docker_commands[1][docker_commands[1].index("--name")+1]
        self.assertEqual(["docker", "network", "create", "--internal", network_name], docker_commands[0])
        self.assertEqual(network_name, docker_commands[1][docker_commands[1].index("--network")+1])
        self.assertEqual("example/squid:v1.0.0", docker_commands[1][-1])
        self.assertEqual(["--cap-drop", "all", "--security-opt", "no-new-privileges:true"], docker_commands[1][docker_commands[1].index("--cap-drop"):docker_commands[1].index("--cap-drop")+4])
        self.assertEqual(["docker", "network", "connect", "bridge", proxy_name], docker_commands[2])
        self.assertEqual(["docker", "rm", "--force", proxy_name], docker_commands[3])
        self.assertEqual(["docker", "network", "rm", network_name], docker_commands[4])
        self.assertTrue(network_name.startswith("scrais-"))
        self.assertTrue(proxy_name.startswith("scrais-proxy-"))
        self.assertEqual(1, len(configuration_files))
        self.assertFalse(os.path.exists(configuration_files[0]))

    def test_sandbox_arguments_announce_the_proxy_and_disable_external_name_resolution(self) -> None:
        # arrange
        egress_proxy = SandboxEgressProxy(["api.example.com"], "example/squid:v1.0.0", False)

        # act
        arguments = egress_proxy.get_sandbox_docker_arguments()

        # assert
        network_name = arguments[arguments.index("--network")+1]
        proxy_address = f"http://{network_name.replace('scrais-', 'scrais-proxy-', 1)}:3128"
        self.assertEqual(["--network", network_name, "--dns", "127.0.0.1", "--env", f"HTTPS_PROXY={proxy_address}", "--env", f"HTTP_PROXY={proxy_address}", "--env", f"https_proxy={proxy_address}", "--env", f"http_proxy={proxy_address}"], arguments)

    def test_failing_proxy_start_removes_what_was_created(self) -> None:
        # arrange
        docker_commands: list[list[str]] = []

        # act
        with self.assertRaisesRegex(ValueError, "failed"):
            self.__run(failing_subcommand="network connect", docker_commands=docker_commands)

        # assert
        self.assertEqual(["connect", "rm"], [docker_commands[2][2], docker_commands[3][1]])
        self.assertEqual(["docker", "network", "rm", docker_commands[0][-1]], docker_commands[4])

    def test_failing_network_creation_removes_only_the_configuration_file(self) -> None:
        # arrange
        docker_commands: list[list[str]] = []

        def run(command, **_):
            docker_commands.append(command)
            return subprocess.CompletedProcess(command, 1, "", "failed")
        egress_proxy = SandboxEgressProxy(["api.example.com"], "example/squid:v1.0.0", False)

        # act
        with mock.patch("subprocess.run", side_effect=run):
            with self.assertRaisesRegex(ValueError, "failed"):
                try:
                    egress_proxy.start()
                finally:
                    egress_proxy.stop()

        # assert
        self.assertEqual(1, len(docker_commands))

    def test_denied_requests_are_shown_in_verbose_mode(self) -> None:
        # arrange
        logs = "1.0 5 172.18.0.3 TCP_TUNNEL/200 39 CONNECT api.example.com:443 - HIER_DIRECT/1.2.3.4 -\n1.1 0 172.18.0.3 TCP_DENIED/403 3 CONNECT other.example.org:443 - HIER_NONE/- text/html\n"

        # act
        docker_commands, _, messages = self.__run(verbose=True, logs=logs)

        # assert
        proxy_name = docker_commands[1][docker_commands[1].index("--name")+1]
        self.assertIn(["docker", "exec", proxy_name, "cat", "/var/log/squid/access.log"], docker_commands)
        self.assertEqual(["The egress-proxy denied the following requests:", "  1.1 0 172.18.0.3 TCP_DENIED/403 3 CONNECT other.example.org:443 - HIER_NONE/- text/html"], messages)

    def test_denied_requests_are_not_read_without_verbose_mode(self) -> None:
        # act
        docker_commands, _, messages = self.__run(verbose=False)

        # assert
        self.assertEqual([], messages)
        self.assertNotIn("exec", [command[1] for command in docker_commands])

    def test_failing_removal_is_reported_with_the_name_of_the_resource(self) -> None:
        # act
        docker_commands, _, messages = self.__run(failing_subcommand="rm")

        # assert
        proxy_name = docker_commands[1][docker_commands[1].index("--name")+1]
        self.assertEqual(1, len(messages))
        self.assertIn(f"proxy-container '{proxy_name}'", messages[0])
