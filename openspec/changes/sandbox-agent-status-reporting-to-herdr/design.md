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
4. **Prerequisite of the image.** The image provides the executable `scrais-agent-status <token>` on the `PATH` and the user-level hook configuration of its agents. The helper appends the token to `/Workspace/Temp/AgentStatus/events` if the folder exists, otherwise it does nothing. It always exits with code 0 and writes nothing to stdout, because hooks of copilot and vibe interpret stdout as a response and a non-zero exit as a failure. The prerequisite with a reference implementation of the helper is documented in `RunAgentInSandbox.md`.
5. **Hook mapping in the image** (to be confirmed per agent in the spike task). Every agent uses the same three-step rule: prompt or agent activity reports `working`, a decision request reports `blocked`, and the end of a turn reports `idle`. A tool event after the decision moves the state from `blocked` back to `working`.

   | Agent | Configuration | working | blocked | idle | Source |
   | --- | --- | --- | --- | --- | --- |
   | claude | `~/.claude/settings.json` | `UserPromptSubmit`, `PostToolUse` | `Notification` | `Stop` | not verified |
   | codex | `hooks.json`, feature flag and trust hash set at image build | `UserPromptSubmit`, tool event | `PermissionRequest` | `Stop` | secondary source |
   | copilot | `~/.copilot/hooks/*.json` | `userPromptSubmitted`, `postToolUse` | `notification` with type `permission_prompt` or `elicitation_dialog` | `agentStop` | official documentation |
   | opencode | plugin with `event` hook in the global configuration | `session.status` | permission events | `session.idle` | secondary source, names differ between versions |
   | vibe | `~/.vibe/hooks.toml` | `pre_tool`, `post_tool` | none | `post_agent`, main agent only | official documentation |

   Known limits, documented per agent:

   - vibe has no event for prompt submission, so `working` starts with the first tool call and a turn without a tool shows no `working`.
   - vibe has no event for an approval request. `pre_tool` runs before the approval prompt, so `blocked` can not be reported and the state stays `working` while vibe waits for approval.
   - `post_agent` of vibe also fires for subagents, so the hook has to match the main agent only.
   - Whether `Notification` of claude fires for real decisions when approvals are skipped is an assumption.
6. **Screen watching as a uniform alternative is rejected.** A wrapper around the agent in the image could derive the states from the terminal output, and it would close the gaps of vibe. It is rejected because it is heuristic, depends on the terminal output of each version, and sits between `exec` and the agent, so signals would no longer reach the agent directly.
7. **Three tokens, no `ended`.** The end of the run is always the end of the container, because the agent is started with `exec`. This works in the same way for every agent, including agents without an end event. An additional token would add a second way to reach the same result.
8. **Components in `scrais`** (each small, each in its own module, none of them knows a concrete agent):
   - `AgentStatus` (enum: working, idle, blocked) and the token parser.
   - `AgentStatusEventChannel`: creates the host folder and the empty `events` file, sets permissions so that any container user can append (mode `0o777` for the folder and `0o666` for the file, because the user id of the container is unknown), returns the docker mount arguments, and removes the folder at the end.
   - `AgentStatusRelay`: runs in a background thread for as long as `docker run` runs, reads new lines from the events file, and forwards valid states to an `AgentStatusReporter`. It is stopped when `docker run` returns, followed by one final read. It is a file read, not a wait-until-it-works retry.
   - `AgentStatusReporter` (interface) with `HerdrAgentStatusReporter` (builds the CLI calls, timeout of a few seconds, failures only logged in verbose mode, sequence number from `time.time_ns()`) and a recording double for tests.
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
- An initialization-script can replace the agent configuration and remove the hooks. Then the report stops, and the agent keeps running.
- A file poll adds a small delay (below a second) to the indicator.
- Writable mounted folder: the container can write arbitrary content into it; mitigated by the closed vocabulary (decision 2). The container can still report wrong states and write a large file, so the relay reads with a limit per line and forwards only changes of the state.
- The open permissions of the event folder allow other local users of the host to write tokens during a run. The impact is limited to a wrong status indicator.
- According to a herdr discussion, a pane of a custom agent can stay labelled with the agent name after a clean quit. To be checked in the spike.

## Open Questions

- Can codex hooks be enabled and trusted completely at image build?
- Which configuration path of each agent is not replaced by usual initialization-scripts?
