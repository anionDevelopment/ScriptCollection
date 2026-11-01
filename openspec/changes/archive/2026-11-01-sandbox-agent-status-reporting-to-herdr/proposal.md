# Proposal

## Why

When `scrais` runs an agent in a sandbox container, the status indicator of that agent in herdr stays without a meaningful state. herdr determines the state of an agent from the foreground process of the pane and from the terminal output.
In the pane only `scrais` and its child `docker` are visible, and the agent runs inside the container.
Screen detection does not work for this setup, and setting the agent via environment variable does not help because the state is still missing. herdr offers a documented way to report the state explicitly (`pane report-agent`), but nothing in the sandbox uses it.

## What Changes

- `scrais` reports the working state of the sandboxed agent to herdr (working, idle, blocked) and releases the agent when the container ends.
- The feature covers all coding-agents of `scrais`: claude, copilot, codex, vibe and opencode.
- All agents are handled on the same way. `scrais` contains no agent-specific status code and no special case for a single agent.
- The container side only writes fixed state tokens into an event file, and `scrais` on the host validates the tokens and forwards them to herdr with the herdr CLI. The herdr socket is never made available inside the container.
- The image is responsible for the container side: it provides one status helper and the hook configuration of its agents. This is a documented prerequisite of the image.
- If the image does not fulfill the prerequisite, then the status report does not work, but the agent runs as usual. Running an agent without herdr or without status support in the image always works.
- Outside of herdr (no herdr environment variables) nothing is reported and nothing changes for the user.
- The command-line interface of `scrais` stays unchanged (no argument and no configuration key is added), and the feature works on Windows, macOS and Linux hosts.
- `RunAgentInSandbox.md` documents the feature, the image prerequisite and the limits.

## Capabilities

### New Capabilities

- `agent-sandbox-status-reporting`: reporting of the state of an agent which runs in the agent sandbox to herdr, including the prerequisite for the image and the isolation rules for the channel between container and host.

### Modified Capabilities

## Impact

- `ScriptCollection/ScriptCollection/AgentRunner.py` (container start, additional mount, start token in the entrypoint, relay lifecycle) and new agent-agnostic modules for event channel, relay and herdr reporter.
- The SCBuilder image (separate repository): status helper and hook configuration for all five agents. Without this work the feature has no effect, and the image tag used by repositories has to be raised afterwards.
- `ScriptCollection/Other/Reference/ReferenceContent/Articles/RunAgentInSandbox.md` and the changelog.
- New testcases for token validation, relay, reporter and uniform handling of the agents (no herdr, no docker, no server needed).
- No new dependency. herdr is only called through its CLI when the herdr environment variables are present.
