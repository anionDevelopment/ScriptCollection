# Tasks

## 1. Shared build-environment-component

- [ ] 1.1 Add a test which records the docker-arguments and environment-variables of `scbuildcodeunits -c` (and `scupdatedependencies` in a container) for a test-repository with required variables, custom-scripts-folder, image-registries-file, `TFCPS`-folder and a `TrustedRootCA_<name>_Path`; verify it passes before the refactoring
- [ ] 1.2 Create `TFCPS/ContainerBuildEnvironment.py` with `ContainerMount`, `run_host_preparation_hook`, `get_mounts` and `get_environment_variables`, and move the root-CA-collection there; verify with new unit-tests (mounts exist/not exist, read-only-flags, duplicate CA-name rejected)
- [ ] 1.3 Use the component in `TFCPS_CodeUnit_BuildCodeUnits.__run_scriptcollection_executable_in_container`; verify the test of 1.1 still passes unchanged

## 2. Package-source-registration as own component and command

- [ ] 2.1 Move the NuGet-registration from `TFCPS_CodeUnitSpecific_DotNet` into `TFCPS/DotNet/NuGetPackageSourceRegistration.py` and call it from there; verify the existing DotNet-tests pass and a test for "same url under other name is updated" and "nothing declared changes nothing" passes
- [ ] 2.2 Add executable `scregisterpackagesources -r <folder>` in `Executables.py` and its entry-point in the package-definition; verify `scregisterpackagesources --help` works after a local install
- [ ] 2.3 Document `scregisterpackagesources` in the reference (where the other executables are documented) and add a changelog-entry; verify the documented call runs as written

## 3. Build-environment in scrais

- [ ] 3.1 Add `provide_build_environment` to `AgentRunnerConfiguration`, `__load_configuration` (optional, default off, `getboolean`) and argument `-b`/`--providebuildenvironment` in `Executables.py`; adapt `test_arguments_of_scrais_are_unchanged`; verify tests for "not defined", "argument overrides file", "invalid value fails"
- [ ] 3.2 In `AgentRunner.__run_sandbox`, if enabled: run the host-hook, add mounts and `--env <name>`, pass the values via `env=` of `subprocess.run`, use the image-entrypoint instead of `--entrypoint sh`, print the secrets-warning to stderr; verify with tests on the generated docker-command (no secret-value in the arguments, no docker-socket, unchanged command when disabled)
- [ ] 3.3 Extend the generated `Entrypoint.sh` with the check for `scregisterpackagesources` and its call before the initialization-script; verify with tests on the entrypoint-content (order, LF-line-endings, missing-command-message)
- [ ] 3.4 Manually verify with `CCOTFunctionsBitcoin` and a SCBuilder-image containing the new ScriptCollection: `scrais -b true -i`, then `dotnet restore` in `CCOTBitcoinLibrary` succeeds, the root-CA is trusted with `drop_capabilities = true`, and the user-level NuGet-configuration (not a repository-`NuGet.config`) was changed
- [ ] 3.5 Document the key, the argument, the image-requirement (entrypoint with `exec "$@"`, ScriptCollection-version) and the secrets-warning in `RunAgentInSandbox.md` and `ConfigurationFolder.md`, add a changelog-entry; verify the documented example-configuration starts the sandbox

## 4. Integration

- [ ] 4.1 Run `scbuildcodeunits` for the repository; verify build, tests and linting pass without new warnings

## Workflow follow-up

- Release ScriptCollection and an SCBuilder-image with that version, then raise `image` in the repositories which use the feature.
- Coordinate with change `sandbox-nested-docker` regarding its requirement "the command-line-interface of scrais stays unchanged".
- Archive the change after review.
