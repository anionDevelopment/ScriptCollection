# Tasks

## 1. Shared build-environment-component

- [x] 1.1 Add a test which records the docker-arguments and environment-variables of `scbuildcodeunits -c` (and `scupdatedependencies` in a container) for a test-repository with required variables, custom-scripts-folder, image-registries-file, `TFCPS`-folder and a `TrustedRootCA_<name>_Path`; verify it passes before the refactoring
- [x] 1.2 Create `TFCPS/ContainerBuildEnvironment.py` with `ContainerMount`, `run_host_preparation_hook`, `get_mounts` and `get_environment_variables`, and move the root-CA-collection there; verify with new unit-tests (mounts exist/not exist, read-only-flags, duplicate CA-name rejected)
- [x] 1.3 Use the component in `TFCPS_CodeUnit_BuildCodeUnits.__run_scriptcollection_executable_in_container`; verify the test of 1.1 still passes unchanged

## 2. Package-source-registration as own component and command

- [x] 2.1 Move the NuGet-registration from `TFCPS_CodeUnitSpecific_DotNet` into `TFCPS/DotNet/NuGetPackageSourceRegistration.py` and call it from there; verify the existing DotNet-tests pass and a test for "same url under other name is updated" and "nothing declared changes nothing" passes
- [x] 2.2 Add executable `scregisterpackagesources -r <folder>` in `Executables.py` and its entry-point in the package-definition; verify `scregisterpackagesources --help` works after a local install
- [x] 2.3 Document `scregisterpackagesources` in the reference (where the other executables are documented) and add a changelog-entry; verify the documented call runs as written

## 3. Build-environment in scrais

- [x] 3.1 Add `provide_build_environment` to `AgentRunnerConfiguration`, `__load_configuration` (optional, default off, `getboolean`) and argument `-b`/`--providebuildenvironment` in `Executables.py`; adapt `test_arguments_of_scrais_are_unchanged`; verify tests for "not defined", "argument overrides file", "invalid value fails"
- [x] 3.2 In `AgentRunner.__run_sandbox`, if enabled: run the host-hook, add mounts and `--env <name>`, pass the values via `env=` of `subprocess.run`, use the image-entrypoint instead of `--entrypoint sh`, print the secrets-warning to stderr; verify with tests on the generated docker-command (no secret-value in the arguments, no docker-socket, unchanged command when disabled)
- [x] 3.3 Extend the generated `Entrypoint.sh` with the check for `scregisterpackagesources` and its call before the initialization-script; verify with tests on the entrypoint-content (order, LF-line-endings, missing-command-message)

## 4. Integration

- [x] 4.1 Run `scbuildcodeunits` for the repository; verify build, tests and linting pass without new warnings

## Workflow follow-up

- Release ScriptCollection and an SCBuilder-image with that version, then raise `image` in the repositories which use the feature.
- Coordinate with change `sandbox-nested-docker` regarding its requirement "the command-line-interface of scrais stays unchanged".
- Archive the change after review.
