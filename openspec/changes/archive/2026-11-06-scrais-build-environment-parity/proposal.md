# Proposal

## Why

An agent started with `scrais` can not restore dependencies from private package-sources (for example the NuGet-feed of
`CCOTLibrary` which `CCOTFunctionsBitcoin` needs), while `scbuildcodeunits -c` can build the same repository in a container.
The reason is that `scbuildcodeunits -c` provides a build-environment to its container (required environment-variables, the
`TFCPS`-configuration-folder, custom scripts, image-registries-file, trusted root-CAs) and `scrais` provides none of it.

## What Changes

- New: `scrais` can provide the same build-environment to the agent-sandbox which `scbuildcodeunits -c` provides to its
  build-container: the required environment-variables of the repository (including the machine-wide additional ones), the
  `TFCPS`-configuration-folder (read-only), the custom-scripts-folder for containers, the image-registries-file and the trusted
  root-CA-certificates. Before the sandbox is started the host-hook `CustomPreCodeUnitBuildScriptForContainer.py` is run, like
  for `scbuildcodeunits -c`.
- New: when the build-environment is provided, the declared package-sources (`Dependency_<technology>_<name>_*`) are registered
  in the sandbox before the agent starts, so that the agent can use them directly (for example with `dotnet restore`) and not
  only through `scbuildcodeunits`.
- New: when the build-environment is provided, the trusted root-CA-certificates are installed in the sandbox before the agent
  starts.
- New: the build-environment is opt-in: new key `provide_build_environment` in `.ScriptCollection/AgentSandboxConfiguration.ini`
  and new argument `-b`/`--providebuildenvironment true|false` of `scrais`, which overrides the value from the configuration-file.
  Without both, nothing changes compared to today.
- New: the command-line-tool `scregisterpackagesources` registers the declared package-sources on the current machine. It is
  the same registration which every DotNet-codeunit-build does already.
- The preparation of the build-environment is moved out of `TFCPS_CodeUnit_BuildCodeUnits` into one component which is used
  by `scbuildcodeunits -c` and by `scrais`, so that both can not diverge. The behavior of `scbuildcodeunits -c` does not change.
- Not part of the parity: the docker-socket (see change `sandbox-nested-docker`), the mount of a base-folder above the
  repository and the update of ScriptCollection inside the container. The sandbox uses the ScriptCollection of its image.

## Capabilities

### New Capabilities

- `agent-sandbox-build-environment`: the build-environment (environment-variables, configuration, scripts, certificates,
  package-sources) which the agent-sandbox gets on request, identical to the one of a local build-container.

### Modified Capabilities

## Impact

- Code: `AgentRunner.py`, `Executables.py` (`scrais`-argument, new executable), `TFCPS/TFCPS_CodeUnit_BuildCodeUnits.py`
  (preparation is moved out), `TFCPS/DotNet/TFCPS_CodeUnitSpecific_DotNet.py` (registration is moved out), new component for the
  build-environment and for the package-source-registration, `setup.py`/`pyproject` entry-point for `scregisterpackagesources`.
- Tests: `test_AgentRunner.py` (including `test_arguments_of_scrais_are_unchanged`, which has to be adapted to the new argument),
  new tests for the shared component.
- Documentation: `RunAgentInSandbox.md`, `ConfigurationFolder.md`, changelog.
- Image: the feature requires an image whose ScriptCollection contains `scregisterpackagesources` (that is a SCBuilder-version
  which is released after this change). With an older image the sandbox-start fails with a clear message if the
  build-environment is requested.
- Security: with the build-environment the agent (which runs with approve-all) can read every secret of the `TFCPS`-folder of
  the host. That is accepted deliberately (decision of the user) and is the reason why the feature is opt-in.
- Interaction: change `sandbox-nested-docker` requires that the command-line-interface of `scrais` stays unchanged apart from
  the removal of `--mountdockersocket`. This change adds an argument and a configuration-key; whichever change is applied
  second has to take that into account.
