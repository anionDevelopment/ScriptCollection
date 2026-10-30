# Running an AI-coding-agent in a sandbox with scrais

## Purpose

`scrais` ("rais" stands for "run agent in sandbox") starts an AI-coding-agent (for example the claude-CLI) for a git-repository inside a short-lived OCI-container instead of directly on the machine.

The purpose is to be able to always let AI-agents run unattended in a sandbox, with one simple command.

An unattended agent executes commands on its own, without anybody approving them. Running it like that on the host is a security-risk, because it can access everything the user can access (other repositories, the home-folder, credentials, the whole file-system). The sandbox is what increases the security: inside the container the agent sees only:

- the repository it should work in (mounted read-write),
- the [additional folders](#additional-folders) given with `-a` (mounted read-write),
- what the used image contains,
- what an optional [initialization-script](#initialization-scripts) sets up.

Because the damage an agent can do is limited to the container and the mounted repository, `scrais` starts every agent in non-interactive mode with its "approve everything"-switch (see [Supported agents](#supported-agents)), so it can work without asking for permission. The interactive mode uses the same sandbox when a user wants to work together with the agent. For `claude` and `copilot` the "approve everything"-switch is also used in interactive mode, so the user is only asked for decisions about the task and not for permissions.

The container is removed (`docker run --rm`) as soon as the agent has finished, so every run starts from the state of the image.

## Prerequisites

- Docker must be installed and the docker-daemon must be reachable for the current user. The container always runs Linux.
- The used image must contain the CLI of the selected coding-agent. `scrais` installs nothing into the container. The SCBuilder-image (`aniondev/scbuilder`) contains all supported agents.
- If an [initialization-script](#initialization-scripts) is used, the image must also contain `bash`.

## Usage

`scrais` must be run in the top-level-folder of a git-repository; otherwise it aborts.

```bat
cd C:\Projects\MyRepository
scrais -i
```

| Argument | Description |
| --- | --- |
| `-p`, `--prompt` | Prompt which is passed to the agent. Required in non-interactive mode, optional in interactive mode. |
| `-i`, `--interactive` | Runs the agent interactively (with a terminal attached). Without this switch the agent runs non-interactively and ends when it has processed the prompt. |
| `-c`, `--codingagent` | Coding-agent to use: `claude`, `codex`, `copilot`, `opencode` or `vibe`. Overrides the [configuration-file](#configuration). |
| `--image` | Image to use, see [Image](#image). Overrides the configuration-file. |
| `-s`, `--dropcapabilities` | `true` or `false`, see [Configuration](#configuration). Overrides the configuration-file. |
| `-a`, `--additionalfolder` | Folder which is additionally mounted read-write into the container, see [Additional folders](#additional-folders). Can be given multiple times. |
| `-d`, `--mountdockersocket` | Mounts the docker-socket of the host into the container, see [Docker-socket](#docker-socket). Dangerous; can only be set via this argument and not in the configuration-file. |
| `-r`, `--repository` | Repository whose [initialization-script](#initialization-scripts) is used. Defaults to the current working-directory. |
| `-v`, `--verbose` | Enables verbose output. |

Typical calls:

```bat
rem start the configured agent interactively without an initial prompt and give it instructions in the session
scrais -i

rem start it interactively with an initial prompt
scrais -i -p "Explain the structure of this repository."

rem let it work on its own and end afterwards
scrais -p "Fix the failing tests."

rem use another agent than the configured one, only for this run
scrais -i -c vibe

rem make two additional folders available to the agent
scrais -i -a C:\Temp\MyFolder -a C:\Data\OtherFolder
```

> The repository which is mounted into the container is always the current working-directory. `-r` only selects which entry of the initialization-scripts-file is used, so it is normally not given.

### Additional folders

Every folder given with `-a`/`--additionalfolder` is mounted read-write to `/Workspace/Other/AdditionalResources/<folder-name>`, so the folder-name is preserved. Example: `-a C:\Temp\MyFolder` is available in the container as `/Workspace/Other/AdditionalResources/MyFolder`.

- A relative path is resolved against the current working-directory.
- The folder must exist; otherwise `scrais` aborts.
- The folder-names must be unique, because they are the mount-targets. Two folders with the same name (for example `C:\A\Data` and `C:\B\Data`) can not be given together.
- Every change of the agent in such a folder ends up directly in the folder on the host.

### Docker-socket

By default the agent has no access to docker. With `--mountdockersocket` the docker-socket of the host (`/var/run/docker.sock`) is mounted into the container, so the `docker`-CLI of the image works with the docker-daemon of the host. A one-line warning is printed to stderr at every start.

> **Caution:** Whoever can use the docker-socket is de facto administrator of the docker-daemon of the host. The agent can start arbitrary (also privileged) containers with arbitrary host-mounts, read and change files outside of the repository, read secrets of other containers and execute code which survives the end of the run. The restrictions of the sandbox (mounted folders, `drop_capabilities`) are ineffective then. Use this switch only for trusted repositories and prompts.

- The switch is deliberately not available in the [configuration-file](#configuration), so that it is a conscious decision for every run.
- Bind-mounts of `docker run -v` are resolved by the daemon on the host, not inside the container. Paths of the container (for example `/Workspace/<repository>`) do not exist there.
- `scbuildcodeunits -c` and `scbuildcodeunitsc` detect that they run in a container. They then start the build-container with the volumes of the sandbox (`--volumes-from`), so the repository has the same path there, and copy the files of the [configuration-folder](./ConfigurationFolder.md) which would normally be mounted into the created container instead of mounting them. Copied files are not read-only.

### Exit-code

The exit-code of `scrais` is the exit-code of the container:

- if the initialization-script fails, the exit-code of the initialization-script (the agent is not started then),
- otherwise the exit-code of the agent.

## Configuration

The configuration of a repository is stored in `<repository>/.ScriptCollection/AgentSandboxConfiguration.ini`:

```ini
[AgentSandboxConfiguration]
codingagent = claude
image = aniondev/scbuilder:v1.2.13
drop_capabilities = true
```

| Key | Meaning |
| --- | --- |
| `codingagent` | The agent which is started: `claude`, `codex`, `copilot`, `opencode` or `vibe`. |
| `image` | The image the container is started from, see [Image](#image). |
| `drop_capabilities` | If `true`, the container is started with `--cap-drop all` and `--security-opt no-new-privileges:true`. This hardens the sandbox but can break tools in the image which need a Linux-capability. |

Every key can also be given as command-line-argument (`--codingagent`, `--image`, `--dropcapabilities`). A value given on the command-line overrides the value from the file. The file itself is optional: it is only required for the values which are not given on the command-line. If a value is neither given on the command-line nor defined in the file, `scrais` aborts with an error which names the missing value.

### Image

The value of `image` (in the file or via `--image`) can have one of two forms:

1. **An image-name from `<repository>/.ScriptCollection/OCIImages/ImageDefinition.csv`** (for example `SCBuilder`). The image is then resolved with the usual image-mechanism of ScriptCollection: the custom registry from `~/.ScriptCollection/GlobalCache/OCIImages/ImageRegistries.csv` is used if it provides the image, otherwise the upstream-registry from `ImageDefinition.csv`. The tag is always the `DefaultTag` from `ImageDefinition.csv`. See [Custom OCI-registries](./CustomOCIRegistries.md).
2. **An image-address including tag** (for example `aniondev/scbuilder:v1.2.13`). It is used as it is.

If the value is neither an image-name from `ImageDefinition.csv` nor an address with a tag, `scrais` aborts.

## Supported agents

| `codingagent` | CLI | Interactive mode | Non-interactive mode |
| --- | --- | --- | --- |
| `claude` | Claude Code | `claude --dangerously-skip-permissions [prompt]` | `claude --print --dangerously-skip-permissions <prompt>` |
| `codex` | OpenAI Codex | `codex [prompt]` | `codex exec --dangerously-bypass-approvals-and-sandbox <prompt>` |
| `copilot` | GitHub Copilot CLI | `copilot --allow-all-tools --allow-all-paths [prompt]` | `copilot --allow-all-tools --allow-all-paths <prompt>` |
| `opencode` | opencode | `opencode [prompt]` | `opencode run <prompt>` |
| `vibe` | Mistral Vibe | `vibe [prompt]` | `vibe --auto-approve --prompt <prompt>` |

`scrais` only starts the agent; it does not configure it. Credentials, settings, skills etc. which the agent needs inside the container have to come from the image or from an [initialization-script](#initialization-scripts).

## What the container looks like

- The repository is mounted read-write to `/Workspace/<repository-folder-name>`, which is also the working-directory of the agent. Every change of the agent ends up directly in the repository on the host.
- The entrypoint of the image is replaced by a generated script (`/Workspace/Entrypoint.sh`). It runs the initialization-script (if there is one) and then replaces itself with the agent (`exec`), so signals like Ctrl+C reach the agent directly. This also means that a custom entrypoint of the image is not run.
- The [additional folders](#additional-folders) are mounted read-write to `/Workspace/Other/AdditionalResources/<folder-name>`.
- Nothing else of the host is mounted. The network is not restricted.

## Initialization-scripts

An initialization-script prepares the container before the agent starts. The typical use is to make the credentials and the configuration of the agent available, which a fresh container does not have, for example:

- writing the token of the agent into its configuration-file,
- configuring git-credentials,
- installing additional tools or packages.

### Declaring an initialization-script

Initialization-scripts are declared per machine (not per repository) in `~/.ScriptCollection/RunAIInSandbox/InitializationScripts.csv`. The first line is a header-line; every further line maps a repository to its script:

```csv
Repository;ScriptFile
C:\Projects\MyRepository;C:\Users\me\AgentInitialization\MyRepository.sh
C:\Projects\OtherRepository;C:\Users\me\AgentInitialization\OtherRepository.sh
```

- `Repository` is the absolute path of the repository on the host. It is compared with the repository of the run as absolute path (case-insensitive on Windows).
- `ScriptFile` is the path of the script on the host.
- A repository without entry (or a machine without this file) is run without initialization-script.

Because this file lives on the machine and not in the repository, a script can contain machine-specific values and secrets without them ever being part of a repository.

### How the script is run

1. The script-file is mounted read-only into the container at `/Workspace/Temp/InitializationScript.sh`.
2. The entrypoint runs it with `bash`, in the working-directory of the agent (the repository).
3. If the script ends with an exit-code other than 0, the container ends with that exit-code and the agent is not started.
4. Afterwards the entrypoint tries to delete the script and then starts the agent.

Things to consider when writing a script:

- **Use LF line-endings.** The script runs on Linux; CRLF line-endings break it.
- **Environment-variables do not reach the agent.** The script runs in its own process, so an `export` in the script is lost when the script ends. Everything the agent needs must be written to files (for example into the configuration-files of the agent in the home-folder of the container).
- **Treat the content of the script as visible to the agent.** The script is mounted read-only, so the deletion in step 4 does not succeed and the agent can still read the script. Only put secrets into it which the agent may know anyway.
- **The script runs on every start.** The container is removed after every run, so the script sets up the same state each time.

### Example

The following script makes a token available to claude by writing it into the settings-file of claude, where claude reads it as environment-variable:

```bash
#!/bin/bash
set -e
mkdir -p ~/.claude
cat > ~/.claude/settings.json <<'EOF'
{
  "env": {
    "CLAUDE_CODE_OAUTH_TOKEN": "<token>"
  }
}
EOF
```

With the matching line in `InitializationScripts.csv`, running `scrais -i` in that repository starts claude already authenticated.
