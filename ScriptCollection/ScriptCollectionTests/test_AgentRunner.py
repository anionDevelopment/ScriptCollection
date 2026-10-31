import argparse
import os
import subprocess
import unittest
from unittest import mock
from ..ScriptCollection import AgentRunner as AgentRunnerModule
from ..ScriptCollection.AgentRunner import AgentRunner, AgentRunnerConfiguration, CodingAgent
from ..ScriptCollection.AgentStatusReporting.AgentStatusEventChannel import AgentStatusEventChannel
from ..ScriptCollection.AgentStatusReporting.AgentStatusReportingSession import AgentStatusReportingSession
from ..ScriptCollection.AgentStatusReporting.HerdrAgentStatusReporter import HerdrAgentStatusReporter
from ..ScriptCollection.Executables import RunAgentInSandbox


HERDR_ENVIRONMENT: dict[str, str] = {"HERDR_ENV": "1", "HERDR_PANE_ID": "w1:p1", "HERDR_BIN_PATH": "herdr"}


class ContainerStart:
    docker_command: list[str] = None
    entrypoint: str = None
    exit_code: int = None
    herdr_commands: list[list[str]] = None

    def __init__(self):
        self.docker_command = None
        self.entrypoint = None
        self.exit_code = None
        self.herdr_commands = []

    def get_status_arguments(self) -> list[str]:
        # Everything of the docker-command which belongs to the status-report. The host-folder is random, so only the target of the mount is compared.
        return [argument.rsplit(":", 1)[-1] for argument in self.docker_command if "AgentStatus" in argument]

    def get_status_lines(self) -> list[str]:
        return [line for line in self.entrypoint.splitlines() if AgentStatusEventChannel.status_helper in line]


class AgentRunnerTests(unittest.TestCase):

    def __start_container(self, environment: dict[str, str], codingagent: CodingAgent = CodingAgent.Claude, prompt: str = None, docker_exit_code: int = 0) -> ContainerStart:
        # Replaces docker: the runner is executed up to the call of "docker run", which then reads the generated entrypoint before it is removed again.
        container_start = ContainerStart()
        configuration = AgentRunnerConfiguration()
        configuration.codingagent = codingagent
        configuration.image = "example/image:v1.0.0"
        configuration.drop_capabilities = True

        def run(command, **_):
            if command[0] != "docker":
                container_start.herdr_commands.append(command)
                return subprocess.CompletedProcess(command, 0)
            container_start.docker_command = command
            entrypoint_file = next(argument for argument in command if argument.endswith(":/Workspace/Entrypoint.sh:ro")).removesuffix(":/Workspace/Entrypoint.sh:ro")
            with open(entrypoint_file, encoding="utf-8", newline="") as file:
                container_start.entrypoint = file.read()
            return subprocess.CompletedProcess(command, docker_exit_code)

        # The image is given as address, so the repository does not have to be a real one and the image-definition-file does not have to exist.
        with mock.patch.object(AgentRunnerModule, "OCIImageManager") as oci_image_manager:
            oci_image_manager.return_value.get_repository_image_definition_file.return_value = "NotExistingFile"
            with mock.patch.dict(os.environ, environment, clear=True):
                with mock.patch("subprocess.run", side_effect=run):
                    container_start.exit_code = AgentRunner(False)._AgentRunner__run_sandbox(os.getcwd(), configuration, prompt, True, None, [])  # pylint: disable=protected-access
        return container_start

    def test_nothing_changes_outside_of_herdr(self) -> None:
        # act
        container_start = self.__start_container({})

        # assert
        self.assertEqual([], container_start.get_status_arguments())
        self.assertEqual([], container_start.get_status_lines())
        self.assertEqual([], container_start.herdr_commands)

    def test_mount_and_start_line_exist_inside_of_herdr(self) -> None:
        # act
        container_start = self.__start_container(HERDR_ENVIRONMENT)

        # assert
        self.assertEqual(["/Workspace/Temp/AgentStatus"], container_start.get_status_arguments())
        self.assertEqual(1, len(container_start.get_status_lines()))
        self.assertTrue(container_start.get_status_lines()[0].endswith("|| true"))

    def test_start_line_is_directly_before_the_agent(self) -> None:
        # act
        lines = self.__start_container(HERDR_ENVIRONMENT).entrypoint.splitlines()

        # assert
        self.assertIn("scrais-agent-status", lines[-2])
        self.assertTrue(lines[-1].startswith("exec claude"))

    def test_start_state_depends_on_the_prompt(self) -> None:
        # act and assert
        self.assertIn("scrais-agent-status working ", self.__start_container(HERDR_ENVIRONMENT, prompt="Do something.").get_status_lines()[0])
        self.assertIn("scrais-agent-status idle ", self.__start_container(HERDR_ENVIRONMENT).get_status_lines()[0])

    def test_entrypoint_has_lf_line_endings(self) -> None:
        # act and assert
        self.assertNotIn("\r", self.__start_container(HERDR_ENVIRONMENT).entrypoint)

    def test_herdr_is_not_available_in_the_container(self) -> None:
        # act
        container_start = self.__start_container({**HERDR_ENVIRONMENT, "HERDR_SOCKET_PATH": "/tmp/herdr.sock"})

        # assert
        self.assertNotIn("/tmp/herdr.sock", " ".join(container_start.docker_command))
        self.assertNotIn("HERDR", " ".join(container_start.docker_command))
        self.assertNotIn("--env", container_start.docker_command)
        self.assertNotIn("HERDR", container_start.entrypoint)

    def test_all_agents_are_handled_on_the_same_way(self) -> None:
        # act
        container_starts = [self.__start_container(HERDR_ENVIRONMENT, codingagent) for codingagent in CodingAgent]

        # assert
        self.assertEqual(5, len(container_starts))
        for container_start in container_starts:
            self.assertEqual(container_starts[0].get_status_arguments(), container_start.get_status_arguments())
            self.assertEqual(container_starts[0].get_status_lines(), container_start.get_status_lines())

    def test_reports_of_all_agents_only_differ_in_the_agent_name(self) -> None:
        for codingagent in CodingAgent:
            # arrange
            reporter = HerdrAgentStatusReporter.try_create(HERDR_ENVIRONMENT, f"scrais-{codingagent.value}", False)

            # act
            command = reporter.get_release_command()

            # assert
            self.assertEqual(["herdr", "pane", "release-agent", "w1:p1", "--source", "scrais", "--agent", f"scrais-{codingagent.value}", "--seq"], command[:-1])

    def test_no_release_for_an_image_without_status_support(self) -> None:
        # act
        container_start = self.__start_container(HERDR_ENVIRONMENT)

        # assert
        self.assertEqual([], container_start.herdr_commands)

    def test_exit_code_of_the_container_is_kept(self) -> None:
        # act and assert
        self.assertEqual(3, self.__start_container(HERDR_ENVIRONMENT, docker_exit_code=3).exit_code)

    def test_agent_starts_if_the_channel_can_not_be_created(self) -> None:
        # act
        with mock.patch("tempfile.mkdtemp", side_effect=PermissionError("denied")):
            container_start = self.__start_container(HERDR_ENVIRONMENT, docker_exit_code=3)

        # assert
        self.assertEqual(3, container_start.exit_code)
        self.assertEqual([], container_start.get_status_arguments())
        self.assertEqual([], container_start.get_status_lines())

    def test_agent_starts_if_reading_the_status_can_not_be_started(self) -> None:
        # act
        with mock.patch("threading.Thread.start", side_effect=RuntimeError("can't start new thread")):
            container_start = self.__start_container(HERDR_ENVIRONMENT, docker_exit_code=3)

        # assert
        self.assertEqual(3, container_start.exit_code)

    def test_exit_code_is_kept_if_finishing_the_report_fails(self) -> None:
        # act
        with mock.patch.object(AgentStatusReportingSession, "_AgentStatusReportingSession__finish", side_effect=OSError("failed")):
            container_start = self.__start_container(HERDR_ENVIRONMENT, docker_exit_code=3)

        # assert
        self.assertEqual(3, container_start.exit_code)

    def test_arguments_of_scrais_are_unchanged(self) -> None:
        # arrange
        expected_arguments = [
            ("help", ("-h", "--help"), None),
            ("prompt", ("-p", "--prompt"), None),
            ("repository", ("-r", "--repository"), None),
            ("interactive", ("-i", "--interactive"), False),
            ("codingagent", ("-c", "--codingagent"), None),
            ("image", ("--image",), None),
            ("dropcapabilities", ("-s", "--dropcapabilities"), None),
            ("additionalfolder", ("-a", "--additionalfolder"), None),
            ("mountdockersocket", ("-d", "--mountdockersocket"), False),
            ("verbose", ("-v", "--verbose"), False),
        ]
        parsers: list[argparse.ArgumentParser] = []

        def capture_parser(parser: argparse.ArgumentParser) -> None:
            parsers.append(parser)
            raise SystemExit(0)

        # act
        with mock.patch.object(argparse.ArgumentParser, "parse_args", capture_parser):
            with self.assertRaises(SystemExit):
                RunAgentInSandbox()

        # assert
        actual_arguments = [(action.dest, tuple(action.option_strings), None if action.dest == "help" else action.default) for action in parsers[0]._actions]  # pylint: disable=protected-access
        self.assertEqual(sorted(expected_arguments), sorted(actual_arguments, key=lambda argument: argument[0]))
