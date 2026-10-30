# Tasks

## 1. Verification spike (not committed as testcases)

- [ ] 1.1 Verify with a real herdr that `pane report-agent` with source `scrais` and agent `scrais-claude` shows the expected indicator colors for working, idle, blocked, and that `release-agent` clears it.
- [ ] 1.2 Verify claude: `--settings <file>` with hooks `UserPromptSubmit`, `Notification`, `Stop`, `SessionEnd` fires in the container when `--dangerously-skip-permissions` is used; record the tested version.
- [ ] 1.3 Verify codex: hooks delivery without replacing the image configuration (hooks.json, feature flag, trust hash); record the tested version.
- [ ] 1.4 Verify opencode: plugin delivery path and the event names `session.status`, `session.idle`, permission events; record the tested version.
- [ ] 1.5 Update design.md decisions 4 and the open questions with the results.

## 2. Core (agent-agnostic)

- [ ] 2.1 Add `AgentStatus` with the token parser that accepts exactly working, idle, blocked, ended.
- [ ] 2.2 Add `AgentStatusReporter` interface and `HerdrAgentStatusReporter` (argument-list command, no shell, timeout, verbose-only failures, `time.time_ns()` sequence, activation only when HERDR_ENV is 1 and pane id and binary path are present).
- [ ] 2.3 Add `AgentStatusEventChannel` (host folder, `report.sh`, docker mount arguments, cleanup).
- [ ] 2.4 Add `AgentStatusRelay` (incremental read of the events file, validation, forwarding, final read on stop).
- [ ] 2.5 Add the `AgentStatusAdapter` interface and the registry keyed by `CodingAgent`.

## 3. Adapters

- [ ] 3.1 Implement `ClaudeStatusAdapter`.
- [ ] 3.2 Implement `CodexStatusAdapter`.
- [ ] 3.3 Implement `OpenCodeStatusAdapter`.

## 4. Integration

- [ ] 4.1 Wire channel, relay, adapter and reporter into `AgentRunner.run` / `__run_sandbox` (start before `docker run`, stop and release in `finally`, start state depends on prompt).
- [ ] 4.2 Ensure no mount, no extra argument and no herdr call exists when outside herdr or without adapter; add the one-time verbose note for agents without adapter.

## 5. Tests (no herdr, docker or server)

- [ ] 5.1 Token parser: accepted tokens, rejected lines (shell syntax, paths, empty, case variants).
- [ ] 5.2 Relay with a recording reporter: ordering, ignoring invalid lines, final read after stop.
- [ ] 5.3 Herdr reporter command building: argument list, source, agent name, state, increasing sequence; inactive without environment variables.
- [ ] 5.4 Adapter content per agent (generated hook files contain the expected events and call `report.sh`).
- [ ] 5.5 AgentRunner: docker command contains the extra mount only when reporting is active.
- [ ] 5.6 Interface guard: argument definitions of `scrais` are unchanged.
- [ ] 5.7 Platform behavior: Windows path conversion of the mount, LF line endings of the helper and adapter files, program path with spaces and `.exe`.

## 6. Documentation and finish

- [ ] 6.1 Update `RunAgentInSandbox.md` (feature, supported agents, behavior outside herdr, security notes, tested versions).
- [ ] 6.2 Add changelog entry.
- [ ] 6.2a Manual verification on Windows, macOS and Linux inside herdr (not committed as testcases).
- [ ] 6.3 Run `scbuildcodeunits` and make sure it succeeds.
- [ ] 6.4 Write the summary into the log file in `Other/Logs`.
