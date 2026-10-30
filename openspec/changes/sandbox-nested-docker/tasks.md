# Tasks

## 1. Verification spike (not committed as testcases)

- [ ] 1.1 Decide with the user the docker engine of the target hosts per platform (design open question 1).
- [ ] 1.1a Determine for Windows, macOS and Linux which backend fulfils all safety requirements; if one platform has none, go back to the user.
- [ ] 1.2 Verify on such a host: `docker run --runtime=sysbox-runc` with the SCBuilder image, `dockerd` starts, `docker run hello-world` and `docker build` work, `docker ps` shows only private containers.
- [ ] 1.3 Verify that a nested container cannot reach host paths (bind mount of a host path outside the mounts) and that nothing remains on the host after the run.
- [ ] 1.4 Verify the combination with `drop_capabilities = true`; record the result in design.md.
- [ ] 1.5 Check the microVM alternative for fit (own image, mounts, initialization script, agents) and record the result in design.md.

## 2. Core

- [ ] 2.1 Add `NestedDockerBackend` interface and `SysboxBackend` (prerequisite check, extra arguments, extra entrypoint lines).
- [ ] 2.2 Add `assert_no_unsafe_arguments` with the forbidden list from the spec.
- [ ] 2.3 Add the host and image prerequisite check with injectable information sources; it returns the missing prerequisite or nothing.

## 3. Integration

- [ ] 3.2 Wire the backend into `__run_sandbox` and `__get_entrypoint_script_content` (daemon start before the initialization script, only when the prerequisites are met).
- [ ] 3.3 Remove `mount_docker_socket`, the socket mount and `__print_docker_socket_warning` from `AgentRunner.py` and the argument `-d/--mountdockersocket` from `Executables.py`; start the backend when the prerequisites are met, otherwise print one stderr line and proceed unchanged.
- [ ] 3.4 Implement the per-platform backend selection.

## 4. Tests (no docker, no server)

- [ ] 4.1 Run arguments with prerequisites met contain the backend arguments and no forbidden argument; with prerequisites missing the arguments are as before.
- [ ] 4.2 Prerequisite check: missing runtime, missing daemon in image, `drop_capabilities` conflict, success (test doubles); the message names the prerequisite.
- [ ] 4.3 Entrypoint content with and without the daemon start.
- [ ] 4.4 Interface guard: a testcase compares the argument definitions of `scrais` (names, short names, actions, defaults) with the expected list; the only difference to before is the missing `-d/--mountdockersocket`, which is rejected.
- [ ] 4.5 Backend selection per platform (platform supplied by a test double) and Windows path conversion of mounts.

## 5. Documentation and finish

- [ ] 5.1 Replace the "Docker-socket" section in `RunAgentInSandbox.md` by the new section (prerequisites per platform, limits, removed switch) and remove the table row of `-d`.
- [ ] 5.2 Add changelog entry marking the removal of the switch (breaking).
- [ ] 5.2a Manual verification on Windows, macOS and Linux (not committed as testcases).
- [ ] 5.3 Run `scbuildcodeunits` and make sure it succeeds.
- [ ] 5.4 Write the summary into the log file in `Other/Logs`.
