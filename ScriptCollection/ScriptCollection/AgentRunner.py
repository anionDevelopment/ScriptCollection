import os
import subprocess
import configparser
import shlex
import tempfile
from enum import Enum
from .GeneralUtilities import GeneralUtilities
from .ScriptCollectionCore import ScriptCollectionCore
from .OCIImages.OCIImageManager import OCIImageManager


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

    @GeneralUtilities.check_arguments
    def __init__(self):
        self.codingagent = None
        self.image = None
        self.drop_capabilities = None


class AgentRunner:
    """AgentRunner ("rais" stands for "run agent in sandbox") runs an AI-coding-agent (for example the claude-CLI) interactively in a sandboxed environment."""
    verbose: bool = None

    @GeneralUtilities.check_arguments
    def __init__(self, verbose: bool):
        self.verbose = verbose

    @GeneralUtilities.check_arguments
    def run(self, prompt: str, interactive: bool, repository: str, configuration_overrides: AgentRunnerConfiguration) -> int:
        # Returns the exit-code of the container, which is the exit-code of the initialization-script if it failed and the exit-code of the agent otherwise.
        # In interactive mode the prompt is optional: without a prompt the agent is started without an initial instruction and the user can instruct it interactively.
        # Every value of configuration_overrides which is not None overrides the corresponding value from the configuration-file.
        GeneralUtilities.assert_condition(interactive or prompt is not None, "A prompt is required when the agent is not run in interactive mode.")
        self.__assert_is_git_root_dir()
        agentRunnerConfiguration: AgentRunnerConfiguration = self.__load_configuration(configuration_overrides)
        initialization_script = self.__get_initialization_script(repository)
        return self.__run_sandbox(agentRunnerConfiguration, prompt, interactive, initialization_script)

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
    def __assert_is_git_root_dir(self) -> None:
        current_working_directory = os.getcwd()
        ScriptCollectionCore().assert_is_git_repository(current_working_directory)
        repository_root = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=current_working_directory, capture_output=True, text=True, check=False)
        GeneralUtilities.assert_condition(repository_root.returncode == 0 and os.path.normcase(os.path.realpath(repository_root.stdout.strip())) == os.path.normcase(os.path.realpath(current_working_directory)), f"The current working-directory '{current_working_directory}' is not the top-level-directory of its git-repository.")

    @GeneralUtilities.check_arguments
    def __load_configuration(self, configuration_overrides: AgentRunnerConfiguration) -> AgentRunnerConfiguration:
        # The configuration-file is optional. Each value is taken from configuration_overrides if it is set there, otherwise from the configuration-file.
        # If a value is neither set in configuration_overrides nor in the configuration-file, an error is raised.
        section = "AgentSandboxConfiguration"
        current_working_directory = os.getcwd()
        agent_sandbox_configuration_file = os.path.join(current_working_directory, ".ScriptCollection", "AgentSandboxConfiguration.ini")
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
        return agentRunnerConfiguration

    @GeneralUtilities.check_arguments
    def __run_sandbox(self, agentRunnerConfiguration: AgentRunnerConfiguration, prompt: str, interactive: bool, initialization_script: str) -> int:
        # The container always runs Linux.
        # The repository is the current working-directory (which was asserted to be the git-root-directory before).
        # It is mounted into the container under "/Workspace/<repository-name>" (preserving the folder-name) and used as working-directory of the agent.
        host_repository_folder = os.getcwd()
        repository_name = os.path.basename(os.path.normpath(host_repository_folder))
        container_workspace_folder = f"/Workspace/{repository_name}"
        agent_command = self.__get_agent_command(agentRunnerConfiguration.codingagent, prompt, interactive)
        # The entrypoint is always used: if an initialization-script is present it runs it first, and then always starts the agent.
        entrypoint_script_content = self.__get_entrypoint_script_content(agent_command, initialization_script)
        entrypoint_file_handle = tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, newline="\n", encoding="utf-8")
        host_entrypoint_file = entrypoint_file_handle.name
        try:
            entrypoint_file_handle.write(entrypoint_script_content)
            entrypoint_file_handle.close()
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
            if initialization_script is not None:
                # The initialization-script is mounted under the fixed path "/Workspace/Temp/InitializationScript.sh"; the entrypoint runs and then removes it before the agent is started.
                # Make the initialization-script executable (chmod +x) too. As for the entrypoint this is effective on Linux-/macOS-hosts; on Windows-hosts it has no effect, which is why it is invoked via "bash" in the entrypoint.
                initialization_script_absolute_path = os.path.abspath(initialization_script)
                os.chmod(initialization_script_absolute_path, 0o755)
                docker_command = docker_command + ["--volume", f"{initialization_script_absolute_path.replace(os.sep, '/')}:/Workspace/Temp/InitializationScript.sh:ro"]
            image = self.__get_image_to_use(agentRunnerConfiguration.image, host_repository_folder)
            docker_command = docker_command + ["--workdir", container_workspace_folder, "--entrypoint", "sh", image, "/Workspace/Entrypoint.sh"]
            # Nothing is installed in the container; the coding-agent-CLI is assumed to be available in the image.
            # subprocess.run blocks until the container has exited, which happens when the agent is finished (or was terminated by the user in interactive mode).
            # The exit-code of the container is returned (and not checked here), so that the caller can pass it through.
            return subprocess.run(docker_command, check=False).returncode
        finally:
            GeneralUtilities.ensure_file_does_not_exist(host_entrypoint_file)

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
    def __get_entrypoint_script_content(self, agent_command: list[str], initialization_script: str) -> str:
        # The entrypoint-script is always used as the container's entrypoint (located at "/Workspace/Entrypoint.sh").
        # It is regenerated before every container-start, so the decision whether the initialization-script is called is made here in python
        # (no runtime-check in the script): if an initialization-script is present its call is included (and the script is removed afterwards),
        # otherwise it is omitted. Afterwards the agent is always started (via exec, so signals reach the agent).
        agent_command_line = shlex.join(agent_command)
        lines = ["#!/bin/sh", "set -e"]
        if initialization_script is not None:
            # The initialization-script is run with bash (and not with sh), so it can use bash-syntax; the image therefore has to contain bash if an initialization-script is used.
            lines.append("bash /Workspace/Temp/InitializationScript.sh")
            lines.append("rm -f /Workspace/Temp/InitializationScript.sh 2>/dev/null || true")
        lines.append(f"exec {agent_command_line}")
        return "\n".join(lines) + "\n"

    @GeneralUtilities.check_arguments
    def __get_agent_command(self, codingagent: CodingAgent, prompt: str, interactive: bool) -> list[str]:
        # Returns the command (including the prompt and - in non-interactive mode - the agent's "approve-all"-switch) which starts the coding-agent-CLI inside the container.
        # Non-interactive mode runs the agent with its switch to approve everything, so it can do whatever it wants inside the (sandboxed) container.
        # For most agents the prompt is passed as the last positional argument; Mistral Vibe is an exception in non-interactive mode (see below).
        # If no prompt is given (only allowed in interactive mode) the agent is started without an initial prompt.
        if codingagent == CodingAgent.Claude:
            agent_command = ["claude"] if interactive else ["claude", "--print", "--dangerously-skip-permissions"]
        elif codingagent == CodingAgent.Codex:
            agent_command = ["codex"] if interactive else ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox"]
        elif codingagent == CodingAgent.Copilot:
            agent_command = ["copilot"] if interactive else ["copilot", "--allow-all-tools"]
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
