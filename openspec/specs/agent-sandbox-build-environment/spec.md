# Agent Sandbox Build Environment Specification

## Purpose

Provides the agent-sandbox of `scrais` on request with the same build-environment which `scbuildcodeunits -c` provides to a
local build-container, so that an agent can build and restore a repository with private dependencies.

## Requirements

### Requirement: Build-environment is opt-in
`scrais` SHALL provide the build-environment only if it is enabled. It is enabled by the key `provide_build_environment` in
`.ScriptCollection/AgentSandboxConfiguration.ini` or by the argument `--providebuildenvironment` (`-b`) with the value `true`
or `false`. The argument SHALL override the configuration-file. If neither defines it, the build-environment SHALL NOT be provided.

#### Scenario: Neither file nor argument define it
- **WHEN** `scrais` is started and neither the configuration-file nor the arguments define `provide_build_environment`
- **THEN** the sandbox is started exactly as without this feature

#### Scenario: Argument overrides the configuration-file
- **WHEN** the configuration-file contains `provide_build_environment = true` and `scrais` is started with `--providebuildenvironment false`
- **THEN** the build-environment is not provided

#### Scenario: Enabled only by argument
- **WHEN** the configuration-file does not contain the key and `scrais` is started with `--providebuildenvironment true`
- **THEN** the build-environment is provided

#### Scenario: Invalid value in the configuration-file
- **WHEN** the configuration-file contains a value for `provide_build_environment` which is not a boolean
- **THEN** `scrais` fails before a container is started

### Requirement: Same build-environment as a local build-container
If the build-environment is enabled, the sandbox SHALL get the same environment-variables, mounts and certificates which
`scbuildcodeunits -c` gives a build-container started directly on the same host for the same repository, except the docker-socket
and the mount of a base-folder above the repository.

#### Scenario: Required environment-variables
- **WHEN** the repository declares required environment-variables in `.ScriptCollection/ProductInformation.xml` and the build-environment is enabled
- **THEN** these variables, the variables of `AdditionalRequiredEnvironmentVariables.txt` and the `TrustedRootCA_<name>_ContentBase64`-variables are set in the sandbox with the values which `scbuildcodeunits -c` would resolve

#### Scenario: Mounted configuration
- **WHEN** the build-environment is enabled and the `TFCPS`-folder, the custom-scripts-folder for containers and the image-registries-file exist on the host
- **THEN** they are available in the sandbox at the same paths and with the same access-mode (read-only or writable) as in a build-container of `scbuildcodeunits -c`

#### Scenario: Optional parts do not exist on the host
- **WHEN** the build-environment is enabled and one of the optional folders or files does not exist on the host
- **THEN** it is not mounted and the sandbox is started anyway, like `scbuildcodeunits -c` does it

#### Scenario: Docker-socket is not part of it
- **WHEN** the build-environment is enabled
- **THEN** the docker-socket of the host is not mounted because of it

### Requirement: Secret values are not exposed in the command-line
Values of environment-variables provided by the build-environment SHALL NOT be part of the arguments of the started
docker-process and SHALL NOT be written to the output of `scrais`, also not in verbose mode.

#### Scenario: Secret in a required environment-variable
- **WHEN** a required environment-variable contains a password and the sandbox is started with the build-environment
- **THEN** the arguments of the docker-process contain only the name of the variable and the password is not in the output

### Requirement: Host-hook runs before the sandbox starts
If the build-environment is enabled, `scrais` SHALL run the host-script `CustomPreCodeUnitBuildScriptForContainer.py` of the
`TFCPS`-configuration-folder (if it exists) with the same arguments as `scbuildcodeunits -c` before it resolves the
environment-variables and starts the sandbox. If the script fails, the sandbox SHALL NOT be started.

#### Scenario: Hook exists
- **WHEN** the build-environment is enabled and the host-script exists
- **THEN** it is run before the container is started

#### Scenario: Hook fails
- **WHEN** the host-script exits with an exit-code other than 0
- **THEN** `scrais` fails and no container is started

### Requirement: Trusted root-CAs are installed before the agent starts
If the build-environment is enabled, the trusted root-CA-certificates declared on the host SHALL be installed in the
trust-store of the sandbox before the agent starts, like it is done in a build-container of `scbuildcodeunits -c`.

#### Scenario: Private feed with a not publicly rooted certificate
- **WHEN** a root-CA is declared via `TrustedRootCA_<name>_Path` on the host and the build-environment is enabled
- **THEN** a tool started by the agent trusts a server whose certificate is signed by that root-CA

### Requirement: Declared package-sources are registered before the agent starts
If the build-environment is enabled, every package-source declared by `Dependency_<technology>_<name>_URL` (and optionally
`_Username` and `_Password`) SHALL be registered with its credentials in the sandbox before the agent starts, so that the agent
can restore dependencies with the tools of the technology directly.

#### Scenario: Private NuGet-feed
- **WHEN** the repository declares `Dependency_CSharp_CCOTLibrary_URL`, `_Username` and `_Password` and the build-environment is enabled
- **THEN** `dotnet restore` started by the agent in a codeunit which uses `CCOTLibrary` resolves the package from that feed

#### Scenario: Registration fails
- **WHEN** the registration of a declared package-source fails
- **THEN** the agent is not started and the exit-code of the container is not 0

### Requirement: Image without the required tooling is rejected clearly
If the build-environment is enabled and the image does not contain the ScriptCollection-command which registers the
package-sources, the sandbox SHALL fail before the agent starts with a message which names the missing command and that a
newer image is required. ScriptCollection SHALL NOT be installed or updated in the sandbox for that.

#### Scenario: Old image
- **WHEN** the build-environment is enabled and the image contains a ScriptCollection-version without `scregisterpackagesources`
- **THEN** the container exits with an exit-code other than 0 and a message naming `scregisterpackagesources` before the agent is started

### Requirement: Registration of package-sources as command-line-tool
The command-line-tool `scregisterpackagesources` SHALL register every declared package-source on the current machine exactly
like a DotNet-codeunit-build does it. A source which is not declared SHALL NOT be changed.

#### Scenario: Run on a machine with an already registered source of the same url
- **WHEN** a declared source is already registered under another name with the same url
- **THEN** that registration is updated with the declared credentials and no second registration is added

#### Scenario: Nothing declared
- **WHEN** no `Dependency_<technology>_<name>_URL`-variable is set
- **THEN** the tool changes nothing and exits with exit-code 0

### Requirement: Build-container behavior is unchanged
`scbuildcodeunits -c` and `scupdatedependencies` in a container SHALL provide the same environment-variables, mounts and
host-hook-run as before this change.

#### Scenario: Container-build after the change
- **WHEN** `scbuildcodeunits -c` is run for a repository
- **THEN** the docker-arguments (apart from their order) and the passed environment-variables are the same as before this change
