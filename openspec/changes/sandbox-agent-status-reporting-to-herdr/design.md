# Design

## Context

Observed facts (from code and herdr documentation, not tested against a real herdr):

- `AgentRunner.__run_sandbox` runs `docker run` as a child process of `scrais` and blocks until the container ends. The
  agent command comes from `__get_agent_command` and is started by a generated entrypoint script.
- herdr injects `HERDR_ENV`, `HERDR_PANE_ID`, `HERDR_BIN_PATH` and `HERDR_SOCKET_PATH` into the processes of a pane. The
  documented reporting call is `"$HERDR_BIN_PATH" pane report-agent <pane> --source <id> --agent <name> --state <state> --seq <n>`
  and `pane release-agent` on exit. States: idle, working, blocked. The CLI works on Windows hosts without touching the
  named pipe.
- The built-in herdr integration for claude only reports the session identity; the state still comes from screen detection.
  Reusing the herdr hooks inside the container therefore does not solve the problem.
- Agents supported by both `scrais` and herdr: claude, codex, opencode. copilot and vibe are not supported by herdr.

## Goals / Non-Goals

Goals: agent-agnostic core with one small adapter per agent; sandbox isolation unchanged; no new dependency; works for
Windows hosts.

Non-Goals: status for copilot and vibe; transmitting messages or titles; reporting resume commands; non-interactive-mode
specific behavior beyond the same states.

## Decisions

1. **Reporting happens on the host.** Only the host has the herdr variables and CLI. Mounting the herdr socket or binary into
   the container is rejected: the herdr API includes `pane run`, which would let the sandbox execute commands on the host and
   defeats the sandbox. A network relay (HTTP) is rejected: it needs a port and a token and has more surface than a file.
2. **File channel with a closed vocabulary.** The container appends one token per line to `events` in a host temp folder that
   is mounted at `/Workspace/Temp/AgentStatus`. Appending short lines is atomic enough for a single writer-at-a-time hook.
   The host accepts only four tokens, so a compromised container cannot inject anything into the herdr call (the command is
   built as an argument list, never through a shell).
3. **Agent-agnostic core, per-agent adapters.** Components (each small, each in its own module):
   - `AgentStatus` (enum: working, idle, blocked, ended) and the token parser.
   - `AgentStatusEventChannel`: creates the host folder, the `report.sh` helper (`echo "$1" >> events`), and returns the
     docker mount arguments; removes the folder at the end.
   - `AgentStatusRelay`: reads new lines from the events file and forwards valid states to an `AgentStatusReporter`.
     Reading is a poll on the file for as long as the container runs (stopped when `docker run` returns, followed by one final
     read). It is a file read, not a wait-until-it-works retry.
   - `AgentStatusReporter` (interface) with `HerdrAgentStatusReporter` (builds the CLI calls, timeout of a few seconds,
     failures only logged in verbose mode, sequence number from `time.time_ns()`) and a recording double for tests.
   - `AgentStatusAdapter` (interface) with `ClaudeStatusAdapter`, `CodexStatusAdapter`, `OpenCodeStatusAdapter`. An adapter
     produces files which make its agent call `report.sh <token>` at its lifecycle events and returns the extra mounts and
     extra agent arguments. The adapter is selected by a registry keyed by `CodingAgent`; a missing entry means no reporting.
4. **Adapter mapping** (to be confirmed per agent in the spike task, because only secondary sources were read for codex and
   opencode):
   - claude: hooks `UserPromptSubmit` to working, `Notification` to blocked, `Stop` to idle, `SessionEnd` to ended, delivered
     with the `--settings <file>` argument so that the image and the user settings stay untouched. Whether `Notification`
     fires only for real decisions when approvals are skipped is an assumption.
   - codex: `hooks.json` with `UserPromptSubmit`, `PermissionRequest`, `Stop` (no session end event exists; the end is
     the container end). Hooks are off by default (feature flag) and trusted by a hash in `config.toml`; how to deliver this
     without replacing the user configuration of the image is an open question for the spike.
   - opencode: a small plugin using the `event` hook (`session.status`, `session.idle`, permission events); delivery path
     into the container configuration is an open question for the spike. Event names differ between versions.
5. **Naming and ordering.** Source `scrais`, agent name `scrais-<codingagent>` (herdr asks not to reuse names of natively
   supported agents), `--seq` from `time.time_ns()`.
6. **Lifecycle in `AgentRunner`.** Before `docker run`: create channel, start relay, report the start state. After `docker run`
   (in the existing `finally`): stop relay, final read, `release-agent`, remove channel. The exit code handling is unchanged.
7. **No fallback logic.** Missing herdr variables or a missing adapter disable the feature explicitly up front (documented
   conditions), instead of trying alternatives at runtime.

## Cross-platform and interface

- No argument and no configuration key is added; activation is derived from `HERDR_ENV`, `HERDR_PANE_ID` and `HERDR_BIN_PATH`.
- The container is always Linux, so the helper and the adapter files are the same on every host. They are written with LF and started
  via `sh` (chmod has no effect on Windows hosts, as for the existing entrypoint).
- The event folder is created in the OS temp folder like the existing entrypoint file and mounted with `replace(os.sep, "/")`.
  Whether the OS temp folder of macOS is shared by default with the docker engine of Docker Desktop is unverified and part of the manual check.
- The herdr call is an argument list with the value of `HERDR_BIN_PATH` as program, so `.exe` and spaces work. Polling the file has no platform-specific API.

## Risks / Trade-offs

- Hook behavior of codex and opencode is unverified; the adapters may need version-specific handling. Mitigation: spike task
  first, pin the tested agent versions in the documentation.
- A file poll adds a small delay (below a second) to the indicator.
- Writable mounted folder: the container can write arbitrary content into it; mitigated by the closed vocabulary (decision 2).
- Windows host path handling for the extra mount must follow the existing `replace(os.sep, "/")` pattern.

## Open Questions

- Final delivery mechanism of the codex and opencode configuration without replacing the configuration of the image.
- Is the home folder of the container user stable across images (relevant for mount targets)?
