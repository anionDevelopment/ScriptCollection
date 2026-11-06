import os
import subprocess
import configparser
import shlex
import tempfile
from enum import Enum
from .GeneralUtilities import GeneralUtilities
from .ScriptCollectionCore import ScriptCollectionCore
from .SCLog import LogLevel
from .OCIImages.OCIImageManager import OCIImageManager
from .TFCPS.ContainerBuildEnvironment import ContainerBuildEnvironment
from .TFCPS.TFCPS_Tools_General import TFCPS_Tools_General
from .AgentStatusReporting.AgentStatusReportingSession import AgentStatusReportingSession
from .AgentSandboxNetwork.SandboxNetworkConfiguration import SandboxNetworkConfiguration, SandboxNetworkMode
from .AgentSandboxNetwork.SandboxEgressProxy import SandboxEgressProxy


class CodingAgent(Enum):
    Copilot = "copilot"
    Claude = "claude"
    OpenCode = "opencode"
    Vibe = "vibe"
    Codex = "codex"


class AgentRunnerConfiguration:
    codingagent: CodingAgent = None
    image: str = None
    drop_capabilities: bool = None
    provide_build_environment: bool = None
    allowed_domains: list[str] = None
    egress_proxy_image: str = None

    @GeneralUtilities.check_arguments
    def __init__(self):
        self.codingagent = None
        self.image = None
        self.drop_capabilities = None
        self.provide_build_environment = None
        # None means that no allowlist is defined (unrestricted network-access); an empty list is an allowlist without domain (no network-access).
        self.allowed_domains = None
        self.egress_proxy_image = None


class SandboxBuildEnvironment:
    """The build-environment (see ContainerBuildEnvironment) prepared for one start of the sandbox: the docker-arguments of its mounts
    and its environment-variables. The values of the environment-variables are typically secrets, so only their names may become
    docker-arguments; the values are given to the docker-client through its own environment."""
    volume_arguments: list[str] = None
    environment_variables: dict[str, str] = None

    def __init__(self, volume_arguments: list[str], environment_variables: dict[str, str]):
        self.volume_arguments = volume_arguments
        self.environment_variables = environment_variables


class AgentRunner:
    """AgentRunner ("rais" stands for "run agent in sandbox") runs an AI-coding-agent (for example the claude-CLI) interactively in a sandboxed environment."""
    verbose: bool = None

    @GeneralUtilities.check_arguments
    def __init__(self, verbose: bool):
        self.verbose = verbose

    @GeneralUtilities.check_arguments
    def run(self, prompt: str, interactive: bool, repository: str, configuration_overrides: AgentRunnerConfiguration, additional_folders: list[str], mount_docker_socket: bool) -> int:
        # Returns the exit-code of the container, which is the exit-code of the initialization-script if it failed and the exit-code of the agent otherwise.
        # In interactive mode the prompt is optional: without a prompt the agent is started without an initial instruction and the user can instruct it interactively.
        # Every value of configuration_overrides which is not None overrides the corresponding value from the configuration-file.
        # additional_folders are absolute host-folders which are additionally mounted (read-write) under "/Workspace/Other/AdditionalResources/<folder-name>".
        # mount_docker_socket is deliberately not part of the configuration-file: it must be a conscious decision for every single run (see __print_docker_socket_warning).
        GeneralUtilities.assert_condition(interactive or prompt is not None, "A prompt is required when the agent is not run in interactive mode.")
        self.__assert_is_git_root_dir(repository)
        agentRunnerConfiguration: AgentRunnerConfiguration = self.__load_configuration(repository, configuration_overrides)
        # The network-configuration is validated before anything is prepared or started, so an invalid allowlist is rejected without side-effects.
        network_configuration = SandboxNetworkConfiguration(agentRunnerConfiguration.allowed_domains, agentRunnerConfiguration.egress_proxy_image)
        initialization_script = self.__get_initialization_script(repository)
        additional_folder_volume_arguments = self.__get_additional_folder_volume_arguments(additional_folders)
        if mount_docker_socket:
            self.__print_docker_socket_warning()
            additional_folder_volume_arguments = additional_folder_volume_arguments + ["--volume", "/var/run/docker.sock:/var/run/docker.sock"]
        build_environment: SandboxBuildEnvironment = None
        if agentRunnerConfiguration.provide_build_environment:
            build_environment = self.__prepare_build_environment(repository)
        return self.__run_sandbox(repository, agentRunnerConfiguration, prompt, interactive, initialization_script, additional_folder_volume_arguments, build_environment, network_configuration)

    @GeneralUtilities.check_arguments
    def __print_docker_socket_warning(self) -> None:
        GeneralUtilities.write_message_to_stderr("Warning: Mounting the docker-socket of the host into the sandbox is dangerous because it makes the sandbox ineffective.")

    @GeneralUtilities.check_arguments
    def __prepare_build_environment(self, repository: str) -> SandboxBuildEnvironment:
        # The sandbox gets the same build-environment as a build-container of "scbuildcodeunits -c" (see ContainerBuildEnvironment), so the agent can
        # build the repository and restore its dependencies (also from private package-sources). The host-hook runs first, like for "scbuildcodeunits -c",
        # because it can create the files the values of the environment-variables are read from. A sandbox has no target-environment of its own;
        # "Development" is passed because the hook expects a valid one and an agent develops the repository.
        sc = ScriptCollectionCore()
        container_build_environment = ContainerBuildEnvironment(sc, TFCPS_Tools_General(sc), repository)
        self.__print_build_environment_warning(sc.get_tfcps_configuration_folder())
        verbosity = LogLevel.Debug if self.verbose else LogLevel.Information
        container_build_environment.run_host_preparation_hook(["--repository", repository, "--targetenvironmenttype", "Development", "--verbosity", str(int(verbosity))])
        volume_arguments: list[str] = []
        for mount in container_build_environment.get_mounts():
            volume_arguments = volume_arguments + ["--volume", f"{mount.source.replace(os.sep, '/')}:{mount.target}{':ro' if mount.read_only else ''}"]
        return SandboxBuildEnvironment(volume_arguments, container_build_environment.get_environment_variables())

    @GeneralUtilities.check_arguments
    def __print_build_environment_warning(self, tfcps_configuration_folder: str) -> None:
        GeneralUtilities.write_message_to_stderr(f"Warning: The build-environment is provided to the sandbox. The agent can read every secret of \"{tfcps_configuration_folder}\" and the values of the required environment-variables of the repository.")

    @GeneralUtilities.check_arguments
    def __get_additional_folder_volume_arguments(self, additional_folders: list[str]) -> list[str]:
        # Every additional folder is mounted under "/Workspace/Other/AdditionalResources/<folder-name>" (preserving the folder-name).
        # Because the folder-name is the mount-target, folder-names must be unique.
        result: list[str] = []
        used_folder_names: list[str] = []
        for additional_folder in additional_folders:
            GeneralUtilities.assert_condition(os.path.isdir(additional_folder), f"The additional folder '{additional_folder}' does not exist.")
            folder_name = os.path.basename(os.path.normpath(additional_folder))
            GeneralUtilities.assert_condition(folder_name != "", f"The additional folder '{additional_folder}' has no folder-name and can therefore not be mounted.")
            GeneralUtilities.assert_condition(folder_name not in used_folder_names, f"The folder-name '{folder_name}' is used by more than one additional folder.")
            used_folder_names.append(folder_name)
            result = result + ["--volume", f"{additional_folder.replace(os.sep, '/')}:/Workspace/Other/AdditionalResources/{folder_name}"]
        return result

    @GeneralUtilities.check_arguments
    def __get_initialization_script(self, repository: str) -> str:
        # The user can define per-repository initialization-scripts in "~/.ScriptCollection/RunAIInSandbox/InitializationScripts.csv".
        # The expected structure is "repository;scriptfile" (one row per repository, acting as a dictionary from repository to initialization-script).
        # If the given repository is listed in the first column (compared as absolute paths), the script-file given in the second column is returned, otherwise None.
        initialization_scripts_file = os.path.join(os.path.expanduser("~"), ".ScriptCollection", "RunAIInSandbox", "InitializationScripts.csv")
        if not os.path.isfile(initialization_scripts_file):
            return None
        normalized_repository = os.path.normcase(os.path.realpath(repository))
        for row in GeneralUtilities.read_csv_file(initialization_scripts_file, ignore_first_line=True):
            if len(row) < 2:
                continue
            if os.path.normcase(os.path.realpath(row[0])) == normalized_repository:
                return row[1]
        return None

    @GeneralUtilities.check_arguments
    def __assert_is_git_root_dir(self, repository: str) -> None:
        ScriptCollectionCore().assert_is_git_repository(repository)
        repository_root = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=repository, capture_output=True, text=True, check=False)
        GeneralUtilities.assert_condition(repository_root.returncode == 0 and os.path.normcase(os.path.realpath(repository_root.stdout.strip())) == os.path.normcase(os.path.realpath(repository)), f"The folder '{repository}' is not the top-level-directory of its git-repository.")

    @GeneralUtilities.check_arguments
    def __load_configuration(self, repository: str, configuration_overrides: AgentRunnerConfiguration) -> AgentRunnerConfiguration:
        # The configuration-file is optional. Each value is taken from configuration_overrides if it is set there, otherwise from the configuration-file.
        # If a value is neither set in configuration_overrides nor in the configuration-file, an error is raised.
        section = "AgentSandboxConfiguration"
        agent_sandbox_configuration_file = os.path.join(repository, ".ScriptCollection", "AgentSandboxConfiguration.ini")
        config_parser = configparser.ConfigParser()
        if os.path.isfile(agent_sandbox_configuration_file):
            config_parser.read(agent_sandbox_configuration_file, encoding="utf-8")
        agentRunnerConfiguration: AgentRunnerConfiguration = AgentRunnerConfiguration()

        if configuration_overrides.codingagent is not None:
            agentRunnerConfiguration.codingagent = configuration_overrides.codingagent
        elif config_parser.has_option(section, "codingagent"):
            codingagent_value = config_parser.get(section, "codingagent")
            allowed_codingagent_values = [coding_agent.value for coding_agent in CodingAgent]
            GeneralUtilities.assert_condition(codingagent_value in allowed_codingagent_values, f"Invalid value '{codingagent_value}' for 'codingagent'. Allowed values are: {', '.join(allowed_codingagent_values)}.")
            agentRunnerConfiguration.codingagent = CodingAgent(codingagent_value)

        if configuration_overrides.image is not None:
            agentRunnerConfiguration.image = configuration_overrides.image
        elif config_parser.has_option(section, "image"):
            agentRunnerConfiguration.image = config_parser.get(section, "image")

        if configuration_overrides.drop_capabilities is not None:
            agentRunnerConfiguration.drop_capabilities = configuration_overrides.drop_capabilities
        elif config_parser.has_option(section, "drop_capabilities"):
            agentRunnerConfiguration.drop_capabilities = config_parser.getboolean(section, "drop_capabilities")

        for name, value in [("codingagent", agentRunnerConfiguration.codingagent), ("image", agentRunnerConfiguration.image), ("drop_capabilities", agentRunnerConfiguration.drop_capabilities)]:
            GeneralUtilities.assert_condition(value is not None, f"The value '{name}' is neither given as argument nor defined in '{agent_sandbox_configuration_file}'.")

        # Unlike the values above, provide_build_environment is not required: the build-environment is opt-in, so it is only provided if it is enabled
        # explicitly. Requiring it would break every existing configuration-file.
        if configuration_overrides.provide_build_environment is not None:
            agentRunnerConfiguration.provide_build_environment = configuration_overrides.provide_build_environment
        elif config_parser.has_option(section, "provide_build_environment"):
            agentRunnerConfiguration.provide_build_environment = config_parser.getboolean(section, "provide_build_environment")
        else:
            agentRunnerConfiguration.provide_build_environment = False

        # The allowlist and egress_proxy_image are not required either: without allowlist the network-access is unrestricted as before. The allowlist is
        # the own section "AllowedDomains" with one entry per domain, whose value is a comment for the reader of the file (for example why the domain is
        # needed); the comment does not influence the behavior. A missing section (no allowlist) and an empty section (allowlist without domain, which
        # blocks the network-access) are distinguished deliberately. A domain which is listed twice is rejected by the parser.
        allowed_domains_section = "AllowedDomains"
        if configuration_overrides.allowed_domains is not None:
            agentRunnerConfiguration.allowed_domains = configuration_overrides.allowed_domains
        elif config_parser.has_section(allowed_domains_section):
            agentRunnerConfiguration.allowed_domains = list(config_parser[allowed_domains_section].keys())

        if configuration_overrides.egress_proxy_image is not None:
            agentRunnerConfiguration.egress_proxy_image = configuration_overrides.egress_proxy_image
        elif config_parser.has_option(section, "egress_proxy_image"):
            agentRunnerConfiguration.egress_proxy_image = config_parser.get(section, "egress_proxy_image")
        return agentRunnerConfiguration

    @GeneralUtilities.check_arguments
    def __run_sandbox(self, repository: str, agentRunnerConfiguration: AgentRunnerConfiguration, prompt: str, interactive: bool, initialization_script: str, additional_folder_volume_arguments: list[str], build_environment: SandboxBuildEnvironment, network_configuration: SandboxNetworkConfiguration) -> int:
        # build_environment is None if the build-environment is not provided.
        # The container always runs Linux.
        # The repository is the folder given by the caller (which was asserted to be the git-root-directory before).
        # It is mounted into the container under "/Workspace/<repository-name>" (preserving the folder-name) and used as working-directory of the agent.
        host_repository_folder = repository
        repository_name = os.path.basename(os.path.normpath(host_repository_folder))
        container_workspace_folder = f"/Workspace/{repository_name}"
        agent_command = self.__get_agent_command(agentRunnerConfiguration.codingagent, prompt, interactive)
        # The status of the agent is reported on the same way for every coding-agent. The session is None if there is nothing to report to.
        status_session = AgentStatusReportingSession.try_create(dict(os.environ), f"scrais-{agentRunnerConfiguration.codingagent.value}", self.verbose)
        status_start_line = None if status_session is None else status_session.get_start_report_line(prompt is not None)
        # The entrypoint is always used: if an initialization-script is present it runs it first, and then always starts the agent.
        entrypoint_script_content = self.__get_entrypoint_script_content(agent_command, initialization_script, status_start_line, build_environment is not None, container_workspace_folder)
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, newline="\n", encoding="utf-8") as entrypoint_file_handle:
            host_entrypoint_file = entrypoint_file_handle.name
            entrypoint_file_handle.write(entrypoint_script_content)
        network_description = network_configuration.get_description()
        if network_description is not None:
            GeneralUtilities.write_message_to_stderr(network_description)
        egress_proxy: SandboxEgressProxy = None
        try:
            # Make the entrypoint-script executable (chmod +x). On Linux-/macOS-hosts the execute-bit propagates into the container; on Windows-hosts this has no effect, which is why the script is additionally invoked via "sh" below.
            os.chmod(host_entrypoint_file, 0o755)
            docker_command = ["docker", "run", "--rm"]
            if interactive:
                # Interactive mode: allocate a pseudo-TTY and keep STDIN open so the agent runs interactively while its STDIO is inherited (variant A).
                docker_command = docker_command + ["--interactive", "--tty"]
            if agentRunnerConfiguration.drop_capabilities:
                docker_command = docker_command + ["--cap-drop", "all", "--security-opt", "no-new-privileges:true"]
            docker_command = docker_command + ["--volume", f"{host_repository_folder.replace(os.sep, '/')}:{container_workspace_folder}"]
            docker_command = docker_command + ["--volume", f"{host_entrypoint_file.replace(os.sep, '/')}:/Workspace/Entrypoint.sh:ro"]
            docker_command = docker_command + additional_folder_volume_arguments
            if initialization_script is not None:
                # The initialization-script is mounted under the fixed path "/Workspace/Temp/InitializationScript.sh"; the entrypoint runs and then removes it before the agent is started.
                # Make the initialization-script executable (chmod +x) too. As for the entrypoint this is effective on Linux-/macOS-hosts; on Windows-hosts it has no effect, which is why it is invoked via "bash" in the entrypoint.
                initialization_script_absolute_path = os.path.abspath(initialization_script)
                os.chmod(initialization_script_absolute_path, 0o755)
                docker_command = docker_command + ["--volume", f"{initialization_script_absolute_path.replace(os.sep, '/')}:/Workspace/Temp/InitializationScript.sh:ro"]
            if status_session is not None:
                docker_command = docker_command + status_session.get_volume_arguments()
            if network_configuration.get_mode() == SandboxNetworkMode.Allowlist:
                # The egress-proxy is assigned before it is started, so the finally-block below also removes what a failing start created.
                egress_proxy = SandboxEgressProxy(network_configuration.allowed_domains, self.__get_image_to_use(network_configuration.egress_proxy_image, host_repository_folder), self.verbose)
                egress_proxy.start()
            docker_command = docker_command + self.__get_network_arguments(network_configuration, egress_proxy)
            # The environment of the docker-client; it differs from the one of this process only if the build-environment is provided.
            docker_client_environment: dict[str, str] = None
            if build_environment is not None:
                docker_command = docker_command + build_environment.volume_arguments
                # Only the names are passed as arguments ("--env <name>" takes the value from the environment of the docker-client), because
                # arguments are visible in the process-list of the host and the values are typically secrets.
                for environment_variable_name in build_environment.environment_variables:
                    docker_command = docker_command + ["--env", environment_variable_name]
                docker_client_environment = {**os.environ, **build_environment.environment_variables}
            image = self.__get_image_to_use(agentRunnerConfiguration.image, host_repository_folder)
            docker_command = docker_command + ["--workdir", container_workspace_folder]
            if build_environment is None:
                docker_command = docker_command + ["--entrypoint", "sh", image, "/Workspace/Entrypoint.sh"]
            else:
                # With the build-environment the entrypoint of the image is kept and runs the generated entrypoint as its command: the entrypoint of the
                # SCBuilder-image installs the trusted root-CA-certificates of the build-environment (and then runs "exec \"$@\""), exactly like in a
                # build-container of "scbuildcodeunits -c". Without the build-environment the entrypoint of the image is replaced as before.
                docker_command = docker_command + [image, "sh", "/Workspace/Entrypoint.sh"]
            # Nothing is installed in the container; the coding-agent-CLI is assumed to be available in the image.
            # subprocess.run blocks until the container has exited, which happens when the agent is finished (or was terminated by the user in interactive mode).
            # The exit-code of the container is returned (and not checked here), so that the caller can pass it through.
            if status_session is not None:
                status_session.start()
            return subprocess.run(docker_command, check=False, env=docker_client_environment).returncode
        finally:
            if status_session is not None:
                status_session.stop()
            if egress_proxy is not None:
                egress_proxy.stop()
            GeneralUtilities.ensure_file_does_not_exist(host_entrypoint_file)

    @GeneralUtilities.check_arguments
    def __get_network_arguments(self, network_configuration: SandboxNetworkConfiguration, egress_proxy: SandboxEgressProxy) -> list[str]:
        # egress_proxy is the started egress-proxy in mode allowlist and None otherwise.
        # Without allowlist no argument is added, so the sandbox is attached to the default bridge-network as before.
        mode = network_configuration.get_mode()
        if mode == SandboxNetworkMode.NoNetwork:
            return ["--network", "none"]
        if mode == SandboxNetworkMode.Allowlist:
            return egress_proxy.get_sandbox_docker_arguments()
        return []

    @GeneralUtilities.check_arguments
    def __get_image_to_use(self, configured_image: str, repository: str) -> str:
        # If the configured image is an image-name defined in "<repository>/.ScriptCollection/OCIImages/ImageDefinition.csv" then the image (address including tag) is resolved
        # using the usual image-mechanism of ScriptCollection: the custom registry from "~/.ScriptCollection/GlobalCache/OCIImages/ImageRegistries.csv" is preferred
        # if it provides the image, otherwise the registry from ImageDefinition.csv is used; the tag is always the DefaultTag from ImageDefinition.csv.
        # Otherwise the configured image is interpreted directly as image-address including tag.
        oci_image_manager = OCIImageManager(ScriptCollectionCore())
        if os.path.isfile(oci_image_manager.get_repository_image_definition_file(repository)) and configured_image in oci_image_manager.get_used_images_in_repository(repository):
            return oci_image_manager.get_registry_address_for_image_with_default_tag(repository, configured_image)
        last_colon_index = configured_image.rfind(":")
        GeneralUtilities.assert_condition(last_colon_index > configured_image.rfind("/") and last_colon_index < len(configured_image) - 1, f"The image '{configured_image}' is neither an image-name defined in the image-definition-file of the repository nor an image-address including a tag.")
        return configured_image

    @GeneralUtilities.check_arguments
    def __get_entrypoint_script_content(self, agent_command: list[str], initialization_script: str, status_start_line: str, provide_build_environment: bool, container_workspace_folder: str) -> str:
        # The entrypoint-script is always used as the container's entrypoint (located at "/Workspace/Entrypoint.sh").
        # It is regenerated before every container-start, so the decision whether the initialization-script is called is made here in python
        # (no runtime-check in the script): if an initialization-script is present its call is included (and the script is removed afterwards),
        # otherwise it is omitted. Afterwards the agent is always started (via exec, so signals reach the agent).
        # status_start_line is None if the status is not reported; it is the only runtime-check, because only the container knows whether its image supports the status-report.
        agent_command_line = shlex.join(agent_command)
        lines = ["#!/bin/sh", "set -e"]
        if provide_build_environment:
            # The declared package-sources are registered before the initialization-script, so that script and the agent can already use them directly
            # (for example with "dotnet restore") and not only through "scbuildcodeunits". The command comes from the ScriptCollection of the image; an
            # image without it is rejected instead of starting the agent without the package-sources.
            lines.append('if ! command -v scregisterpackagesources >/dev/null 2>&1; then echo "The build-environment requires the command \\"scregisterpackagesources\\" of ScriptCollection, which is not available in this image. Use a newer image." >&2; exit 1; fi')
            lines.append(f"scregisterpackagesources -r {shlex.quote(container_workspace_folder)}")
        if initialization_script is not None:
            # A line is written to stdout before the initialization-script runs, so it is unambiguous in the container-output that an initialization-script was configured and executed (without it one cannot tell whether the agent started unconfigured because no script was declared or because a declared script did nothing).
            lines.append('echo "Running initialization-script for the agent-sandbox..."')
            # The initialization-script is run with bash (and not with sh), so it can use bash-syntax; the image therefore has to contain bash if an initialization-script is used.
            lines.append("bash /Workspace/Temp/InitializationScript.sh")
            lines.append("rm -f /Workspace/Temp/InitializationScript.sh 2>/dev/null || true")
        else:
            # The counterpart of the message above: it makes clear that the agent is started unconfigured on purpose because no initialization-script is declared for this repository (see __get_initialization_script).
            lines.append('echo "No initialization-script is configured for this repository; the agent is started without an initialization-script."')
        if status_start_line is not None:
            lines.append(status_start_line)
        lines.append(f"exec {agent_command_line}")
        return "\n".join(lines) + "\n"

    @GeneralUtilities.check_arguments
    def __get_agent_command(self, codingagent: CodingAgent, prompt: str, interactive: bool) -> list[str]:
        # Returns the command (including the prompt and the agent's "approve-all"-switch) which starts the coding-agent-CLI inside the container.
        # Non-interactive mode runs the agent with its switch to approve everything, so it can do whatever it wants inside the (sandboxed) container.
        # Claude and Copilot also get their "approve-all"-switch in interactive mode, so the user is only asked for decisions and not for permissions.
        # For most agents the prompt is passed as the last positional argument; Mistral Vibe is an exception in non-interactive mode (see below).
        # If no prompt is given (only allowed in interactive mode) the agent is started without an initial prompt.
        if codingagent == CodingAgent.Claude:
            agent_command = ["claude", "--dangerously-skip-permissions"] if interactive else ["claude", "--print", "--dangerously-skip-permissions"]
        elif codingagent == CodingAgent.Codex:
            agent_command = ["codex"] if interactive else ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox"]
        elif codingagent == CodingAgent.Copilot:
            agent_command = ["copilot", "--allow-all-tools", "--allow-all-paths"]
        elif codingagent == CodingAgent.OpenCode:
            agent_command = ["opencode"] if interactive else ["opencode", "run"]
        elif codingagent == CodingAgent.Vibe:
            # Mistral Vibe: interactive mode takes the initial prompt as a positional argument, while programmatic (non-interactive) mode
            # expects the prompt via the --prompt-flag and uses --auto-approve to approve all tool-calls.
            if interactive:
                agent_command = ["vibe"]
                if prompt is not None:
                    agent_command = agent_command + [prompt]
            else:
                agent_command = ["vibe", "--auto-approve"]
                if prompt is not None:
                    agent_command = agent_command + ["--prompt", prompt]
            return agent_command
        else:
            raise ValueError(f"Unsupported coding-agent '{codingagent}'.")
        if prompt is not None:
            agent_command = agent_command + [prompt]
        return agent_command
