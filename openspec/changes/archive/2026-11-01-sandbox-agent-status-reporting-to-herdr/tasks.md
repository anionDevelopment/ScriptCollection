# Tasks

## 1. Verification spike (not committed as testcases)

- [x] 1.1 Verify with a real herdr that `pane report-agent` with source `scrais` and agent name `scrais-claude` shows the expected indicator colors for working, idle, blocked, that `release-agent` clears it, and that an unknown name like `scrais-vibe` works in the same way.
- [x] 1.2 Verify claude: the hooks in `/etc/claude-code/managed-settings.json` fire in the container when `--dangerously-skip-permissions` is used; record the tested version.
- [ ] 1.3 Verify codex: the managed hooks in `/etc/codex/requirements.toml` run without a trust decision; record the tested version.
- [ ] 1.4 Verify copilot: `~/.copilot/hooks/*.json` fires with `--allow-all-tools`, including the filter on the `notification` type; record the tested version.
- [ ] 1.5 Verify opencode: the plugin is loaded and the events `session.status`, `permission.asked`, `permission.replied` arrive; record the tested version.
- [ ] 1.6 Verify vibe: `~/.vibe/hooks.toml` fires in interactive and in non-interactive mode; record the tested version.
- [ ] 1.7 Check whether a pane stays labelled after `release-agent`.
- [ ] 1.8 Update design.md decision 5 and the open questions with the results.

## 2. Core in scrais (agent-agnostic)

- [x] 2.1 Add `AgentStatus` with the token parser that accepts exactly working, idle, blocked.
- [x] 2.2 Add `AgentStatusReporter` interface and `HerdrAgentStatusReporter` (argument-list command, no shell, timeout, verbose-only failures, `time.time_ns()` sequence, activation only when HERDR_ENV is 1 and pane id and binary path are present).
- [x] 2.3 Add `AgentStatusEventChannel` (host folder, empty `events` file, permissions for any container user, docker mount arguments, cleanup).
- [x] 2.4 Add `AgentStatusRelay` (background thread, incremental read of the events file with a limit per line, validation, forwarding of state changes only, final read on stop).

## 3. Integration in scrais

- [x] 3.1 Wire channel, relay and reporter into `AgentRunner.run` / `__run_sandbox` (start before `docker run`, stop in `finally`, `release-agent` only if a state was reported).
- [x] 3.2 Add the start token line to the entrypoint (`working` with prompt, `idle` otherwise), directly before `exec` and only when reporting is active; it must not be able to stop the entrypoint.
- [x] 3.3 Ensure no mount, no entrypoint line and no herdr call exists outside herdr, and add the one-time verbose note when no status was received.
- [x] 3.4 Ensure a failing channel or relay does not affect start, run or exit code of the agent.

## 4. Tests in scrais (no herdr, docker or server)

- [x] 4.1 Token parser: accepted tokens, rejected lines (shell syntax, paths, empty, case variants, `ended`).
- [x] 4.2 Relay with a recording reporter: ordering, ignoring invalid and oversized lines, forwarding only changes of the state, final read after stop, no release without a report.
- [x] 4.3 Herdr reporter command building: argument list, source, agent name, state, increasing sequence; inactive without environment variables.
- [x] 4.4 AgentRunner: docker command and entrypoint are unchanged outside herdr, and contain the mount and the start token line inside herdr.
- [x] 4.5 Uniform handling: for every value of `CodingAgent` the status-related docker arguments and entrypoint lines are identical, and reports only differ in the agent name.
- [x] 4.6 Robustness: a failing channel, relay or reporter does not change the exit code and does not prevent the start of the container.
- [x] 4.7 Interface guard: argument definitions of `scrais` are unchanged.
- [x] 4.8 Platform behavior: Windows path conversion of the mount, permissions of the event folder and file, program path with spaces and `.exe`.

## 5. Documentation in scrais

- [x] 5.1 Update `RunAgentInSandbox.md` (feature, image prerequisite with reference implementation of the helper, behavior without herdr and without image support, limits per agent, security notes, tested versions).
- [x] 5.2 Add changelog entry.
- [x] 5.3 Run `scbuildcodeunits` and make sure it succeeds.

## 6. Image (repository SCBuilder)

- [x] 6.1 Add `scrais-agent-status` to the image according to the documented prerequisite (LF line endings, always exit code 0, no stdout).
- [x] 6.2 Add the hook configuration for claude, codex, copilot, opencode and vibe according to design.md decision 5.
- [x] 6.3 Add a check to the image build that the hook configuration of all five agents is present and calls the helper.
- [ ] 6.4 Release the image and raise the image tag in `RunAgentInSandbox.md` and in the sandbox configuration of the repositories which use it.

## 7. Finish

- [ ] 7.1 Manual verification with all five agents on Windows, macOS and Linux inside herdr, plus one run with an image without status support and one run outside herdr (not committed as testcases).
- [x] 7.2 Write the summary into the log file in `Other/Logs`.
