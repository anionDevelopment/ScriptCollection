# Proposal

## Why

When `scrais` runs an agent in a sandbox container, the status indicator of that agent in herdr stays without a meaningful
state. herdr determines the state of an agent from the foreground process of the pane and from the terminal output. In the
pane only `scrais` and its child `docker` are visible, and the agent runs inside the container. Screen detection does not work
for this setup, and setting the agent via environment variable does not help because the state is still missing. herdr offers
a documented way to report the state explicitly (`pane report-agent`), but nothing in the sandbox uses it.

## What Changes

- `scrais` reports the lifecycle and the working state of the sandboxed agent to herdr (working, idle, blocked, released).
- The reports are produced agent-agnostically: the container side only writes fixed state tokens into an event file, and
  `scrais` on the host validates the tokens and forwards them to herdr with the herdr CLI. The herdr socket is never made
  available inside the container.
- For every agent which is supported by `scrais` and by herdr (claude, codex, opencode) a small adapter makes the agent write
  the state tokens at its lifecycle events. Agents without adapter (copilot, vibe) are started as before and report nothing.
- Outside of herdr (no herdr environment variables) nothing is reported and nothing changes for the user.
- The command-line interface of `scrais` stays unchanged (no argument and no configuration key is added), and the feature works on
  Windows, macOS and Linux hosts.
- `RunAgentInSandbox.md` documents the feature and its limits.

## Capabilities

### New Capabilities
- `agent-sandbox-status-reporting`: reporting of the state of an agent which runs in the agent sandbox to herdr, including
  the isolation rules for the channel between container and host.

### Modified Capabilities

## Impact

- `ScriptCollection/ScriptCollection/AgentRunner.py` (container start, additional mount, relay lifecycle) and new modules for
  event channel, relay, herdr reporter and agent adapters.
- `ScriptCollection/Other/Reference/ReferenceContent/Articles/RunAgentInSandbox.md` and the changelog.
- New testcases for token validation, relay and adapters (no herdr, no docker, no server needed).
- No new dependency. herdr is only called through its CLI when the herdr environment variables are present.
