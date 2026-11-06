# Design

## Context

See proposal.md - Why. Observed state of the code:

- `TFCPS_CodeUnit_BuildCodeUnits.__run_scriptcollection_executable_in_container` prepares the build-container: it runs the
  host-hook `CustomPreCodeUnitBuildScriptForContainer.py`, collects mounts (custom-scripts-folder writable, image-registries-file
  read-only, `TFCPS`-folder read-only, root-CA-files read-only via `__collect_trusted_root_ca_arguments`) and resolves the required
  environment-variables (`TFCPS_Tools_General.get_required_environment_variables`). The values are given through the environment of
  the docker-client and only the names are passed as `-e <name>`.
- The package-sources are not registered by the container-start. `TFCPS_CodeUnitSpecific_DotNet.__ensure_declared_package_sources_are_available`
  registers them (`dotnet nuget add/update source`) at the start of every DotNet-codeunit-build, from the `Dependency_CSharp_*`-variables.
- The root-CAs are installed by `EntryPoint.sh` of the SCBuilder-image (`/usr/local/bin/EntryPoint.sh`, `update-ca-certificates`), which
  then runs `exec "$@"`.
- `AgentRunner.__run_sandbox` starts the sandbox with `--entrypoint sh <image> /Workspace/Entrypoint.sh`. So the entrypoint of the image is
  replaced and the root-CAs would not be installed even if they were mounted.
- `AgentRunner.__load_configuration` requires every key (`codingagent`, `image`, `drop_capabilities`) in the file or as argument.

## Goals / Non-Goals

**Goals:**
- One place which defines the build-environment of a container, used by `scbuildcodeunits -c` and `scrais`.
- An agent can use private package-sources directly, without running `scbuildcodeunits`.

**Non-Goals:**
- Starting `scrais` itself inside a container (the `--volumes-from`/`docker cp`-path of the build-container). `scrais` mounts with bind-mounts only, as today.
- Docker in the sandbox, base-folder-mount, ScriptCollection-update in the sandbox (see proposal).
- Restricting which secrets of the `TFCPS`-folder the agent can read (decided: full parity).
- Other technologies than CSharp for the registration. The command is generic in its name, but only the existing CSharp-registration exists.

## Decisions

### 1. Shared component `ContainerBuildEnvironment`

New class in `TFCPS/ContainerBuildEnvironment.py`. Constructed with `ScriptCollectionCore`, `TFCPS_Tools_General` and the repository.
Public operations:
- `run_host_preparation_hook(build_arguments: list[str]) -> None`: runs `CustomPreCodeUnitBuildScriptForContainer.py`.
- `get_mounts() -> list[ContainerMount]`: value-object with `source`, `target`, `read_only`. Includes the root-CA-file-mounts.
- `get_environment_variables() -> dict[str, str]`: required variables plus the inline `TrustedRootCA_*_ContentBase64`-variables.

`__collect_trusted_root_ca_arguments` and `__check_trusted_root_ca_name_is_unique` move into this class without functional change.
`TFCPS_CodeUnit_BuildCodeUnits` converts the mounts into `-v source:target[:ro]` (the format `__copy_mounts_into_container` already
parses). `AgentRunner` converts them into `--volume`-arguments.

Why: the build-environment is a separate responsibility (the class `TFCPS_CodeUnit_BuildCodeUnits` is already large) and a copy into
`AgentRunner` would diverge. A value-object instead of ready docker-arguments, because the two callers handle mounts differently
(bind-mount or `docker cp`). Rejected alternative: `AgentRunner` calls a method of `TFCPS_CodeUnit_BuildCodeUnits`: that would
couple the sandbox to the whole build-class and its constructor-arguments (verbosity, target-environment, ...).

The build-arguments for the hook (`__get_build_arguments`) are created by the caller. `AgentRunner` uses the same format with the
target-environment-type `Development` (assumption: the hook only needs a valid value, a sandbox has no own target-environment).

### 2. Shared component for the registration of package-sources

The registration logic of `TFCPS_CodeUnitSpecific_DotNet` (`__ensure_declared_package_sources_are_available`,
`__get_registered_nuget_sources`, `__nuget_sources_are_equal`, `__remove_nuget_source`) moves into `TFCPS/DotNet/NuGetPackageSourceRegistration.py`
with an operation `register_declared_package_sources(folder: str)`. `TFCPS_CodeUnitSpecific_DotNet` calls it as before with the
codeunit-folder. The new executable `scregisterpackagesources -r <folder>` (in `Executables.py`, entry-point in the package-definition)
calls it with the given folder. Why: same reason as decision 1, and the command is needed inside the sandbox where there is no codeunit-build.

### 3. Sandbox-start with build-environment

If the build-environment is enabled, `AgentRunner.__run_sandbox`:
1. runs the host-hook (decision 1),
2. adds the mounts as `--volume` and the variables as `--env <name>`, and gives the values to `subprocess.run` through `env=`
   (copy of `os.environ` plus the values), like `scbuildcodeunits -c`,
3. does not pass `--entrypoint sh` but runs the image's own entrypoint with the command `sh /Workspace/Entrypoint.sh`. So the SCBuilder-
   `EntryPoint.sh` installs the root-CAs (and runs its `CustomScriptPath`-hook) as in every other container of this image, and then runs
   `exec "$@"`.
4. The generated `Entrypoint.sh` gets before the initialization-script:
   `command -v scregisterpackagesources` (fails with a clear message, see spec) and `scregisterpackagesources -r <container-workspace-folder>`.
   The registration runs before the initialization-script, so that script can already use the sources.

Why the image-entrypoint (3) instead of copying the CA-logic into the generated entrypoint: the logic stays in one place (SCBuilder) and is
identical to the build-container. Rejected: always using the image-entrypoint also without build-environment, because that would change the
behavior of every existing `scrais`-run. Consequence: the build-environment requires an image whose entrypoint ends with `exec "$@"` (SCBuilder).
That is documented.

The registration runs as the user of the image and writes the user-level NuGet-configuration of the sandbox. Like in the build-container,
`--store-password-in-clear-text` is used on Linux (existing behavior).

### 4. Configuration

`AgentRunnerConfiguration` gets `provide_build_environment: bool`. Opt-in (decision of the user): unlike the existing keys it is not required;
if neither argument nor file defines it, it is `False`. This is a deliberate exception from the rule "every key must be defined", because
requiring it would break every existing `AgentSandboxConfiguration.ini`. Argument `-b`/`--providebuildenvironment` with `choices=["true","false"]`,
same pattern as `--dropcapabilities`. `config_parser.getboolean` rejects invalid values.

### 5. ScriptCollection-version in the sandbox

No installation/update in the sandbox (decision of the user). The check in decision 3.4 makes an old image fail clearly instead of
starting the agent without registered sources.

## Risks / Trade-offs

- [The agent can read all secrets of the `TFCPS`-folder of the host, also ones which the repository does not need] → opt-in, warning in
  `RunAgentInSandbox.md`, and `scrais` writes a warning to stderr when the build-environment is enabled (like the docker-socket-warning today).
- [`update-ca-certificates` with `--cap-drop all` and `no-new-privileges` can fail] → the SCBuilder-entrypoint runs as root and writes
  root-owned files, which needs no capability; it has to be verified in task 3. If it fails, the container-start fails visibly (existing
  behavior of the SCBuilder-entrypoint), not silently.
- [`dotnet nuget add source` without `--configfile` changes the nearest `NuGet.config` instead of the user-level one] → unchanged behavior of the
  existing registration; the sandbox calls it in the repository-root, which usually has no `NuGet.config`. Verified in task 3.
- [Refactoring breaks `scbuildcodeunits -c`] → test which compares the docker-arguments and environment-variables before and after (spec
  "Build-container behavior is unchanged").
- [Conflict with change `sandbox-nested-docker` about the CLI] → see proposal, Impact.

## Migration Plan

No migration. Without the new key/argument nothing changes. To use the feature: release ScriptCollection, release an SCBuilder-image with
that version, raise `image` in `AgentSandboxConfiguration.ini` of the repository and set `provide_build_environment = true`. Then manual exports
of tokens in an initialization-script (for example the ones in `CCOTFunctionsBitcoin.sh`) can be removed where they are covered by the
required environment-variables; this is outside of this repository. Rollback: set the key to `false`.
