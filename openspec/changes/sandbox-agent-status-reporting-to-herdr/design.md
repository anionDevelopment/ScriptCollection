# Design

## Context

Observed facts from the code:

- `AgentRunner.__run_sandbox` runs `docker run` as a child process of `scrais` and blocks until the container ends. The agent command comes from `__get_agent_command` and is started with `exec` by a generated entrypoint script, so the container ends when the agent ends.
- `scrais` accepts any image with `--image`. It installs nothing into the container, and the SCBuilder image contains all supported agents.

Statements from third-party documentation (read for this change, not tested):

- herdr injects `HERDR_ENV`, `HERDR_PANE_ID`, `HERDR_BIN_PATH` and `HERDR_SOCKET_PATH` into the processes of a pane. The documented reporting call is `"$HERDR_BIN_PATH" pane report-agent <pane> --source <id> --agent <name> --state <state> --seq <n>` and `pane release-agent` on exit. States: idle, working, blocked.
- Reporting needs no native support of herdr for the agent: a custom integration can use its own agent name. Therefore copilot and vibe can be reported in the same way as the other agents.
- herdr ignores stale sequence numbers of the same source.
- The built-in herdr integration for claude only reports the session identity; the state still comes from screen detection. Reusing the herdr hooks inside the container therefore does not solve the problem.
- All five agents offer hooks or plugins (see decision 5), but with different events.

## Goals / Non-Goals

Goals: status report for all five agents; one uniform way without structural special cases for single agents; sandbox isolation unchanged; running an agent never depends on the feature; no new dependency; works for Windows hosts.

Non-Goals: transmitting messages or titles; reporting resume commands; non-interactive-mode specific behavior beyond the same states; status support for images which do not fulfill the prerequisite.

## Decisions

1. **Reporting happens on the host.** Only the host has the herdr variables and CLI. Mounting the herdr socket or binary into the container is rejected: the herdr API includes `pane run`, which would let the sandbox execute commands on the host and defeats the sandbox. A network relay (HTTP) is rejected: it needs a port and a token and has more surface than a file.
2. **File channel with a closed vocabulary.** The container appends one token per line to `events` in a host temp folder that is mounted at `/Workspace/Temp/AgentStatus`. Appending short lines is atomic enough for a single writer-at-a-time hook. The host accepts only three tokens, so a compromised container cannot inject anything into the herdr call (the command is built as an argument list, never through a shell).
3. **The image owns everything agent-specific.** This is the uniform way: `scrais` knows the channel, and the image connects its agents to that channel. There are no adapters, no registry and no agent arguments in `scrais`. Generating the hook files on the host is rejected: it needs a code path per agent in `scrais`, and the delivery of the configuration was unsolved for codex and opencode.
4. **Prerequisite of the image.** The image provides the executable `scrais-agent-status <token>` on the `PATH` and the hook configuration of its agents. The configuration must survive an initialization-script: the documented example of `RunAgentInSandbox.md` replaces `~/.claude/settings.json` completely, so hooks in that file would be lost. Therefore it is stored in the managed configuration of the agent or in an own file. The helper appends the token to `/Workspace/Temp/AgentStatus/events` if the folder exists, otherwise it does nothing. It always exits with code 0 and writes nothing to stdout, because hooks of copilot and vibe interpret stdout as a response and a non-zero exit as a failure. The prerequisite with a reference implementation of the helper is documented in `RunAgentInSandbox.md`.
5. **Hook mapping in the image.** Every agent uses the same three-step rule: prompt or agent activity reports `working`, a decision request reports `blocked`, and the end of a turn reports `idle`. A tool event after the decision moves the state from `blocked` back to `working`. The mapping comes from the documentation and, where noted, from the source of the version pinned in SCBuilder; no agent has run with it yet (spike tasks).

   | Agent (pinned version) | Configuration | working | blocked | idle | Source |
   | --- | --- | --- | --- | --- | --- |
   | claude (2.1.296) | `/etc/claude-code/managed-settings.json` | `UserPromptSubmit`, `PostToolUse` | `PreToolUse` of `AskUserQuestion`, `PermissionRequest`, `Notification` with `permission_prompt`, `elicitation_dialog`, `elicitation_url_dialog` | `Stop` | documentation |
   | codex (0.162.1) | `/etc/codex/requirements.toml` with the helper in `managed_dir` | `UserPromptSubmit`, `PostToolUse` | `PermissionRequest` | `Stop`, `Interrupt` | documentation, parser of the version |
   | copilot (1.0.96) | `~/.copilot/hooks/scrais-agent-status.json` | `userPromptSubmitted`, `postToolUse` | `notification` with `permission_prompt`, `elicitation_dialog` | `agentStop` | documentation |
   | opencode (1.19.0) | `~/.config/opencode/plugins/scrais-agent-status.js` | `session.status` not `idle`, `permission.replied` | `permission.asked` | `session.status` `idle` | documentation, observations of third parties |
   | vibe (2.26.1) | `~/.vibe/hooks.toml` | `pre_tool`, `post_tool` | none | `post_agent` | documentation, source of the version |

   Managed hooks are used for codex because they are trusted by policy; user hooks would need an interactive trust decision. This replaces the former plan with a trust hash. The feature flag is not needed, because hooks are enabled by default.

   Known limits, documented per agent:

   - vibe has no event for prompt submission, so `working` starts with the first tool call and a turn without a tool shows no `working`.
   - vibe has no event for an approval request. `pre_tool` runs before the approval prompt, so `blocked` can not be reported and the state stays `working` while vibe waits for approval.
   - `post_agent` of vibe also fires for subagents, and version 2.26.1 rejects `match` for this hook type (a rejected entry is skipped), so the end of a subagent reports `idle` until the next tool starts.
   - `Stop` of claude is not documented to fire for a turn interrupted by the user, so the state can stay `working` in that case.
   - claude runs with `--dangerously-skip-permissions`, so `AskUserQuestion` is its main source of `blocked`. Whether the other two events fire in this mode is an assumption.
6. **Screen watching as a uniform alternative is rejected.** A wrapper around the agent in the image could derive the states from the terminal output, and it would close the gaps of vibe. It is rejected because it is heuristic, depends on the terminal output of each version, and sits between `exec` and the agent, so signals would no longer reach the agent directly.
7. **Three tokens, no `ended`.** The end of the run is always the end of the container, because the agent is started with `exec`. This works in the same way for every agent, including agents without an end event. An additional token would add a second way to reach the same result.
8. **Components in `scrais`** (each small, each in its own module, none of them knows a concrete agent):
   - `AgentStatus` (enum: working, idle, blocked) and the token parser.
   - `AgentStatusEventChannel`: creates the host folder and the empty `events` file, sets permissions so that any container user can append (mode `0o777` for the folder and `0o666` for the file, because the user id of the container is unknown), returns the docker mount arguments, and removes the folder at the end.
   - `AgentStatusRelay`: runs in a background thread for as long as `docker run` runs, reads new lines from the events file, and forwards valid states to an `AgentStatusReporter`. A read is limited in size and results in at most one report with the latest state, so that a flood of tokens can not start a flood of processes or delay the end of `scrais`. It is stopped when `docker run` returns, followed by one final read. It is a file read, not a wait-until-it-works retry.
   - `AgentStatusReporter` (interface) with `HerdrAgentStatusReporter` (builds the CLI calls, timeout of a few seconds, failures only logged in verbose mode, sequence number from `time.time_ns()`) and a recording double for tests.
   - `AgentStatusReportingSession`: combines the parts above for one run, so that `AgentRunner` only has to start and stop it, and ensures that a failure never reaches the agent.
9. **Naming and ordering.** Source `scrais`, agent name `scrais-<codingagent>` with the value of `CodingAgent` (herdr asks not to reuse names of natively supported agents), `--seq` from `time.time_ns()`.
10. **Lifecycle in `AgentRunner`.** Before `docker run`: create channel, add mount, add the start token to the entrypoint, start relay. After `docker run` (in the existing `finally`): stop relay, final read, `release-agent` if at least one state was reported, remove channel. The exit code handling is unchanged.
11. **The start state comes from the container.** The generated entrypoint runs, directly before `exec` and only when reporting is active, `command -v scrais-agent-status >/dev/null 2>&1 && scrais-agent-status <start-token> || true`. So `scrais` sends nothing to herdr until the image has proven its support, an image without support stays exactly as today, and a stale `working` is impossible. Because of `|| true` the line can not stop the entrypoint which runs with `set -e`. This is a small runtime check in the entrypoint, which otherwise decides everything in Python; it is accepted because `scrais` can not know the content of the image up front.
12. **Failures never touch the agent.** A failing channel or relay disables the report for this run with a verbose message. This is no fallback mechanism, because no alternative way of reporting is tried. Missing herdr variables disable the feature up front.

## Cross-platform and interface

- No argument and no configuration key is added; activation is derived from `HERDR_ENV`, `HERDR_PANE_ID` and `HERDR_BIN_PATH`.
- The container is always Linux, so the helper and the hook configuration in the image are the same on every host.
- The event folder is created in the OS temp folder like the existing entrypoint file and mounted with `replace(os.sep, "/")`. The agent can only start if this folder is shared with the docker engine anyway, because the existing entrypoint file is mounted from the same location, so the additional mount adds no new requirement for the host.
- The herdr call is an argument list with the value of `HERDR_BIN_PATH` as program, so `.exe` and spaces work. Polling the file has no platform-specific API.

## Risks / Trade-offs

- The status report only works with images which fulfill the prerequisite. This is accepted: running the agent still works with every image.
- ScriptCollection and SCBuilder share a contract (helper name, tokens, path of the event file). A change of it requires a coordinated change in both repositories.
- vibe does not reach the full state set (decision 5). The requirement for all agents is therefore met with documented limits for vibe.
- Hook behavior of the agents is unverified; hooks may change between versions. Mitigation: spike task first, and the agent versions are fixed by the image tag.
- The hook configuration is added to the image, which is also the build image of many repositories. The helper does nothing without the event folder, so builds are not affected.
- A file with invalid content in a managed location could affect the start of an agent. Mitigation: the smoke test of the image build parses every configuration file, and the parser of the pinned codex version was read.
- A file poll adds a small delay (below a second) to the indicator.
- Writable mounted folder: the container can write arbitrary content into it; mitigated by the closed vocabulary (decision 2). The container can still report wrong states and write a large file, so the relay reads with a limit per line and forwards only changes of the state.
- The open permissions of the event folder allow other local users of the host to write tokens during a run. The impact is limited to a wrong status indicator.
- According to a herdr discussion, a pane of a custom agent can stay labelled with the agent name after a clean quit. To be checked in the spike.

## Open Questions

- Do the hooks fire as mapped in decision 5 when the agents run in the real image (spike tasks)?
