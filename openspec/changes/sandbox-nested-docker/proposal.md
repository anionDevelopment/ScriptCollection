# Proposal

## Why

An agent in the sandbox sometimes needs docker (build an image, start a test service). The only way today is
`scrais --mountdockersocket`, which mounts the docker socket of the host. Whoever can use that socket is administrator of the
docker daemon of the host: the agent can start privileged containers with arbitrary host mounts, so the sandbox is
ineffective. The other well-known ways (privileged docker-in-docker, relaxing seccomp or user namespace restrictions) weaken
the sandbox in a similar way. The goal is docker inside the sandbox where everything the agent starts stays inside the
sandbox and no unsafe configuration is needed.

## What Changes

- New requirement: `docker` works inside the sandbox like on a normal machine (no special flags, no `DOCKER_HOST`), against a
  docker daemon which is private to the sandbox container. There is no switch for it: it is available whenever the
  prerequisites (backend on the host, docker daemon in the image) are met.
- New requirement: providing it never needs a privileged container, the host socket, host namespaces, extra capabilities or
  disabled security profiles. If the prerequisites are not met, the sandbox starts without docker and says so; it is never
  weakened to make docker available.
- **BREAKING**: the switch `-d`/`--mountdockersocket` is removed without replacement, together with its warning. `scrais` does
  not support mounting the host socket any more. Command lines which contain the switch fail in argument parsing.
- New requirement: apart from this removal the command-line interface of `scrais` stays unchanged (no argument is added or
  renamed, no configuration key is added).
- New requirement: the feature works on Windows, macOS and Linux hosts.
- The concept (see design) uses one backend per platform behind a common interface (isolating runtime with nested docker, or microVM).
- `RunAgentInSandbox.md` documents the feature and the removal of the old switch.

## Capabilities

### New Capabilities
- `agent-sandbox-docker`: docker usage inside the agent sandbox without access to the daemon, files or resources of the host.

### Modified Capabilities

## Impact

- `AgentRunner.py` (docker start arguments, entrypoint content, removal of the socket mount and its warning),
  `Executables.py` (removal of the argument `-d`), `RunAgentInSandbox.md`, changelog.
- Requirements on the host (an isolating runtime) and on the image (docker daemon and CLI). If they are not met, docker is simply not available.
- Users of `--mountdockersocket` have to remove the switch; docker then works through the private daemon when the prerequisites are met.
- This change is independent of `sandbox-agent-status-reporting-to-herdr`; both touch `AgentRunner.py` and `Executables.py`.
