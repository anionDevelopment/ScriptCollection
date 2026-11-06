import argparse
import os
import subprocess
import tempfile
import unittest
from unittest import mock
from ..ScriptCollection import AgentRunner as AgentRunnerModule
from ..ScriptCollection.AgentRunner import AgentRunner, AgentRunnerConfiguration, CodingAgent, SandboxBuildEnvironment
from ..ScriptCollection.AgentStatusReporting.AgentStatusEventChannel import AgentStatusEventChannel
from ..ScriptCollection.AgentStatusReporting.AgentStatusReportingSession import AgentStatusReportingSession
from ..ScriptCollection.AgentStatusReporting.HerdrAgentStatusReporter import HerdrAgentStatusReporter
from ..ScriptCollection.Executables import RunAgentInSandbox
from ..ScriptCollection.TFCPS.ContainerBuildEnvironment import ContainerMount


HERDR_ENVIRONMENT: dict[str, str] = {"HERDR_ENV": "1", "HERDR_PANE_ID": "w1:p1", "HERDR_BIN_PATH": "herdr"}


class ContainerStart:
    docker_command: list[str] = None
    docker_client_environment: dict[str, str] = None
    entrypoint: str = None
    exit_code: int = None
    herdr_commands: list[list[str]] = None

    def __init__(self):
        self.docker_command = None
        self.docker_client_environment = None
        self.entrypoint = None
        self.exit_code = None
        self.herdr_commands = []

    def get_status_arguments(self) -> list[str]:
        # Everything of the docker-command which belongs to the status-report. The host-folder is random, so only the target of the mount is compared.
        return [argument.rsplit(":", 1)[-1] for argument in self.docker_command if "AgentStatus" in argument]

    def get_status_lines(self) -> list[str]:
        return [line for line in self.entrypoint.splitlines() if AgentStatusEventChannel.status_helper in line]


class AgentRunnerTests(unittest.TestCase):

    def __start_container(self, environment: dict[str, str], codingagent: CodingAgent = CodingAgent.Claude, prompt: str = None, docker_exit_code: int = 0, build_environment: SandboxBuildEnvironment = None, initialization_script: str = None) -> ContainerStart:
        # Replaces docker: the runner is executed up to the call of "docker run", which then reads the generated entrypoint before it is removed again.
        container_start = ContainerStart()
        configuration = AgentRunnerConfiguration()
        configuration.codingagent = codingagent
        configuration.image = "example/image:v1.0.0"
        configuration.drop_capabilities = True

        def run(command, **keyword_arguments):
            if command[0] != "docker":
                container_start.herdr_commands.append(command)
                return subprocess.CompletedProcess(command, 0)
            container_start.docker_command = command
            container_start.docker_client_environment = keyword_arguments.get("env")
            entrypoint_file = next(argument for argument in command if argument.endswith(":/Workspace/Entrypoint.sh:ro")).removesuffix(":/Workspace/Entrypoint.sh:ro")
            with open(entrypoint_file, encoding="utf-8", newline="") as file:
                container_start.entrypoint = file.read()
            return subprocess.CompletedProcess(command, docker_exit_code)

        # The image is given as address, so the repository does not have to be a real one and the image-definition-file does not have to exist.
        with mock.patch.object(AgentRunnerModule, "OCIImageManager") as oci_image_manager:
            oci_image_manager.return_value.get_repository_image_definition_file.return_value = "NotExistingFile"
            with mock.patch.dict(os.environ, environment, clear=True):
                with mock.patch("subprocess.run", side_effect=run):
                    container_start.exit_code = AgentRunner(False)._AgentRunner__run_sandbox(os.getcwd(), configuration, prompt, True, initialization_script, [], build_environment)  # pylint: disable=protected-access
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

    def test_arguments_of_scrais(self) -> None:
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
            ("providebuildenvironment", ("-b", "--providebuildenvironment"), None),
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

    def __load_configuration(self, configuration_file_content: str, provide_build_environment_override: bool) -> AgentRunnerConfiguration:
        with tempfile.TemporaryDirectory() as repository:
            os.makedirs(os.path.join(repository, ".ScriptCollection"))
            with open(os.path.join(repository, ".ScriptCollection", "AgentSandboxConfiguration.ini"), "w", encoding="utf-8") as file:
                file.write("[AgentSandboxConfiguration]\ncodingagent = claude\nimage = example/image:v1.0.0\ndrop_capabilities = true\n" + configuration_file_content)
            overrides = AgentRunnerConfiguration()
            overrides.provide_build_environment = provide_build_environment_override
            return AgentRunner(False)._AgentRunner__load_configuration(repository, overrides)  # pylint: disable=protected-access

    def test_build_environment_is_not_provided_if_it_is_not_defined(self) -> None:
        # act and assert
        self.assertFalse(self.__load_configuration("", None).provide_build_environment)

    def test_build_environment_is_provided_if_the_configuration_file_enables_it(self) -> None:
        # act and assert
        self.assertTrue(self.__load_configuration("provide_build_environment = true\n", None).provide_build_environment)

    def test_build_environment_argument_overrides_the_configuration_file(self) -> None:
        # act and assert
        self.assertFalse(self.__load_configuration("provide_build_environment = true\n", False).provide_build_environment)
        self.assertTrue(self.__load_configuration("", True).provide_build_environment)

    def test_invalid_build_environment_value_in_the_configuration_file_fails(self) -> None:
        # act and assert
        with self.assertRaises(ValueError):
            self.__load_configuration("provide_build_environment = maybe\n", None)

    def test_without_build_environment_the_entrypoint_of_the_image_is_replaced(self) -> None:
        # act
        container_start = self.__start_container({})

        # assert
        self.assertEqual(["--entrypoint", "sh", "example/image:v1.0.0", "/Workspace/Entrypoint.sh"], container_start.docker_command[-4:])
        self.assertIsNone(container_start.docker_client_environment)
        self.assertNotIn("scregisterpackagesources", container_start.entrypoint)

    def test_build_environment_is_given_to_the_container_without_secret_values_in_the_arguments(self) -> None:
        # arrange
        build_environment = SandboxBuildEnvironment(["--volume", "/host/TFCPS:/Workspace/ScriptCollectionConfiguration/TFCPS:ro"], {"Dependency_CSharp_MyFeed_Password": "MySecretPassword"})

        # act
        container_start = self.__start_container({"PATH": "/usr/bin"}, build_environment=build_environment)

        # assert
        self.assertIn("/host/TFCPS:/Workspace/ScriptCollectionConfiguration/TFCPS:ro", container_start.docker_command)
        self.assertEqual("Dependency_CSharp_MyFeed_Password", container_start.docker_command[container_start.docker_command.index("--env")+1])
        self.assertNotIn("MySecretPassword", " ".join(container_start.docker_command))
        self.assertEqual({"PATH": "/usr/bin", "Dependency_CSharp_MyFeed_Password": "MySecretPassword"}, container_start.docker_client_environment)
        self.assertNotIn("/var/run/docker.sock:/var/run/docker.sock", container_start.docker_command)

    def test_with_build_environment_the_entrypoint_of_the_image_is_kept(self) -> None:
        # act
        container_start = self.__start_container({}, build_environment=SandboxBuildEnvironment([], {}))

        # assert
        #the entrypoint of the SCBuilder-image installs the trusted root-CAs and then runs the generated entrypoint as its command.
        self.assertNotIn("--entrypoint", container_start.docker_command)
        self.assertEqual(["example/image:v1.0.0", "sh", "/Workspace/Entrypoint.sh"], container_start.docker_command[-3:])

    def test_with_build_environment_the_package_sources_are_registered_before_the_initialization_script(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as folder:
            initialization_script = os.path.join(folder, "Initialization.sh")
            with open(initialization_script, "w", encoding="utf-8") as file:
                file.write("echo initialized\n")

            # act
            container_start = self.__start_container({}, build_environment=SandboxBuildEnvironment([], {}), initialization_script=initialization_script)

        # assert
        lines = container_start.entrypoint.splitlines()
        check_line = next(index for index, line in enumerate(lines) if "command -v scregisterpackagesources" in line)
        registration_line = next(index for index, line in enumerate(lines) if line.startswith("scregisterpackagesources -r "))
        initialization_line = lines.index("bash /Workspace/Temp/InitializationScript.sh")
        self.assertLess(check_line, registration_line)
        self.assertLess(registration_line, initialization_line)
        #an image without the command must fail with a message which names it instead of starting the agent without the package-sources.
        self.assertIn("exit 1", lines[check_line])
        self.assertIn("scregisterpackagesources", lines[check_line].split("echo", 1)[1])
        self.assertEqual(f"scregisterpackagesources -r /Workspace/{os.path.basename(os.getcwd())}", lines[registration_line])
        self.assertNotIn("\r", container_start.entrypoint)

    def __run_with_build_environment(self, host_preparation_hook_side_effect, events: list[str]) -> None:
        # Runs scrais with the build-environment up to the call of "docker run" and records the order of the host-hook, of the warning and of the container-start in events.
        configuration = AgentRunnerConfiguration()
        configuration.codingagent = CodingAgent.Claude
        configuration.image = "example/image:v1.0.0"
        configuration.drop_capabilities = True
        configuration.provide_build_environment = True

        def run_host_preparation_hook(_):
            events.append("hook")
            if host_preparation_hook_side_effect is not None:
                raise host_preparation_hook_side_effect

        def run(command, **_):
            events.append(command[0])
            return subprocess.CompletedProcess(command, 0)
        agent_runner = AgentRunner(False)
        with mock.patch.object(AgentRunnerModule, "ContainerBuildEnvironment") as container_build_environment, mock.patch.object(AgentRunnerModule, "OCIImageManager") as oci_image_manager:
            container_build_environment.return_value.run_host_preparation_hook.side_effect = run_host_preparation_hook
            container_build_environment.return_value.get_mounts.return_value = []
            container_build_environment.return_value.get_environment_variables.return_value = {}
            oci_image_manager.return_value.get_repository_image_definition_file.return_value = "NotExistingFile"
            with mock.patch.object(agent_runner, "_AgentRunner__assert_is_git_root_dir"), mock.patch.object(agent_runner, "_AgentRunner__get_initialization_script", return_value=None), mock.patch.object(AgentRunnerModule.GeneralUtilities, "write_message_to_stderr", side_effect=lambda _: events.append("warning")):
                # The status-report to herdr is disabled because it would also start programs.
                with mock.patch.dict(os.environ, {name: value for name, value in os.environ.items() if not name.startswith("HERDR")}, clear=True), mock.patch("subprocess.run", side_effect=run):
                    agent_runner.run("Do something.", False, os.getcwd(), configuration, [], False)

    def test_host_hook_runs_before_the_sandbox_starts_and_a_warning_is_printed(self) -> None:
        # arrange
        events: list[str] = []

        # act
        self.__run_with_build_environment(None, events)

        # assert
        self.assertEqual(["warning", "hook", "docker"], events)

    def test_sandbox_is_not_started_if_the_host_hook_fails(self) -> None:
        # arrange
        events: list[str] = []

        # act
        with self.assertRaisesRegex(RuntimeError, "^hook failed$"):
            self.__run_with_build_environment(RuntimeError("hook failed"), events)

        # assert
        self.assertEqual(["warning", "hook"], events)

    def test_mounts_of_the_build_environment_keep_their_access_mode(self) -> None:
        # arrange
        agent_runner = AgentRunner(False)
        with mock.patch.object(AgentRunnerModule, "ContainerBuildEnvironment") as container_build_environment, mock.patch.object(AgentRunnerModule.GeneralUtilities, "write_message_to_stderr"):
            container_build_environment.return_value.get_mounts.return_value = [ContainerMount("/host/CustomScripts", "/Workspace/CustomScripts", False), ContainerMount("/host/TFCPS", "/Workspace/ScriptCollectionConfiguration/TFCPS", True)]
            container_build_environment.return_value.get_environment_variables.return_value = {"MyVariable": "MyValue"}

            # act
            build_environment: SandboxBuildEnvironment = agent_runner._AgentRunner__prepare_build_environment(os.getcwd())  # pylint: disable=protected-access

        # assert
        self.assertEqual(["--volume", "/host/CustomScripts:/Workspace/CustomScripts", "--volume", "/host/TFCPS:/Workspace/ScriptCollectionConfiguration/TFCPS:ro"], build_environment.volume_arguments)
        self.assertEqual({"MyVariable": "MyValue"}, build_environment.environment_variables)
