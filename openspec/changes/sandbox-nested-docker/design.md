# Design

## Context

Observed facts (code):

- `AgentRunner.run` mounts `/var/run/docker.sock` when `mount_docker_socket` is true and prints a warning. The switch is
  CLI-only on purpose. `__run_sandbox` builds the `docker run` command; the entrypoint script (generated per start) runs the
  initialization script and then `exec`s the agent. `drop_capabilities` adds `--cap-drop all` and `no-new-privileges`.
- Nested containers cannot be isolated by the sandbox if they run on the daemon of the host (sibling containers).

External facts (secondary sources, not tested here): Sysbox lets a container run docker without `--privileged` and without a
socket mount via `--runtime=sysbox-runc`; it maps container root to an unprivileged host user, but is not a VM-equivalent
boundary, needs installation on the docker host, and I could not confirm how it works with Docker Desktop on Windows. Docker
Sandboxes run each agent in a microVM with a private docker daemon; Windows support is described as experimental, and its
fit to the `scrais` model (own image, mounts, initialization script, all agents) is unknown.

## Goals / Non-Goals

Goals: normal `docker` in the sandbox, nothing leaves the sandbox, no unsafe configuration, never weaken the sandbox to provide docker.
Non-Goals: persistent image cache between runs, GPU access, nested docker for agents other than via the same mechanism,
making the sandbox stronger than today when docker is not available.

## Alternatives

| Option | Stays in sandbox | Unsafe config needed | Verdict |
| --- | --- | --- | --- |
| Mount host socket (today) | no | the socket itself | removed without replacement switch |
| Socket proxy filtering API calls to the host daemon | no (sibling containers on the host) | filter must catch every dangerous create/build parameter | rejected: large attack surface, fails the requirement that everything stays in the sandbox |
| Privileged docker-in-docker sidecar | no (privileged container is a host breakout) | `--privileged` | rejected |
| Rootless docker or podman inside the container | yes | relaxed seccomp or AppArmor, `/dev/fuse` or extra capabilities | rejected: needs the unsafe settings the requirement forbids (to be re-verified in the spike, because it depends on the host engine) |
| Isolating runtime with nested docker (Sysbox) | yes | none (a different `--runtime`) | preferred first backend |
| MicroVM sandbox with private daemon | yes, strongest | none | candidate second backend; fit to `scrais` unknown |

## Decisions

1. **Isolation backend abstraction.** Introduce `NestedDockerBackend` (interface) with the methods: check host prerequisites,
   return extra `docker run` arguments, return extra entrypoint lines. First implementation: `SysboxBackend`
   (extra argument `--runtime=sysbox-runc`; prerequisite: the runtime is listed by `docker info`). A microVM backend can be
   added later behind the same interface without changing `AgentRunner` or the spec.
2. **Daemon start in the entrypoint.** The generated entrypoint starts the docker daemon in the background before the
   initialization script, when the prerequisites are met. Readiness is needed before the agent starts. A bounded readiness check
   conflicts with the rule "no loop that waits until something works"; it is needed here because the daemon has no
   startup notification. **This needs the explicit approval of the user** (see open questions).
3. **Prerequisite check before start.** `NestedDockerBackend.check` evaluates host runtimes (`docker info` output, injected
   for tests) and image content (`docker run --rm --entrypoint sh <image> -c "command -v dockerd docker"` or equivalent),
   and returns the missing prerequisite, if any. The image check costs one extra container start per run (unmeasured).
4. **Forbidden-argument guard.** A function `assert_no_unsafe_arguments(docker_command)` runs on the final argument list and
   fails the run on any forbidden argument from the spec. It protects against later regressions and is covered by tests.
5. **Always on when possible.** There is no switch. `AgentRunner` asks the backend for its prerequisites on every run. If they are
   met, the backend arguments and the daemon start are added; if not, the run proceeds exactly as today and one stderr line names the
   missing prerequisite. This is not a fallback to something weaker; it is the absence of docker. `mount_docker_socket`,
   `__print_docker_socket_warning`, the socket mount and the argument `-d/--mountdockersocket` are deleted.
6. **Stateless.** The nested daemon storage lives in the container filesystem and disappears with `--rm`.
7. **`drop_capabilities`.** Stays as configured. Whether the nested daemon can run with `--cap-drop all` inside the isolating
   runtime must be verified; if not, docker is unavailable in that combination (message) and the setting is not changed silently.
8. **Images.** The SCBuilder image must contain `dockerd` and the CLI; this is a prerequisite, not installed by `scrais`.

## Cross-platform

- Containers always run Linux; on Windows and macOS the docker engine runs them inside a VM. Sysbox needs a Linux kernel with
  the runtime installed in the engine, so it cannot be assumed for Docker Desktop. A microVM backend (Docker Sandboxes) is
  described for macOS and Windows (experimental) and Linux (container based, legacy) in secondary sources.
- Therefore the backend is selected per platform and engine by `scrais`. The spec demands the same behavior everywhere; whether
  one platform has no backend which fulfils the safety requirements is only known after the spike. In that case docker is unavailable on that platform and this requirement
  has to be revisited with the user; the safety requirements are not relaxed.
- Mounts and scripts follow the existing patterns (`replace(os.sep, "/")`, scripts written with LF and started via `sh`/`bash`).

## Risks / Trade-offs

- Sysbox is not a VM-equivalent boundary: a kernel vulnerability can still reach the host. For the strongest guarantee the
  microVM backend is the better target; the abstraction keeps that door open.
- Host support is the main uncertainty: it must be installed on the docker engine of the host and I could not confirm it for a
  Windows host with Docker Desktop. If it is not available there, the feature would work only on Linux hosts or WSL engines at first.
- Nested containers have the same network access as the sandbox.
- Starting a daemon in every run (when possible) costs startup time and enlarges the attack surface slightly compared to a switch. A switch or configuration key would avoid that but contradicts the unchanged-interface requirement.
- Pulling images in every run costs time and bandwidth (no cache by design).

## Open Questions

1. Which docker engine runs on the hosts that matter (Docker Desktop on Windows and macOS, Docker Engine in WSL2, Linux)? This decides the backend per platform, and whether all three platforms can be served.
2. May the entrypoint contain a bounded readiness check for the daemon (decision 2)?
3. Assumption to confirm: with no switch left, docker is provided automatically whenever the prerequisites are met (the alternative would be no way to use docker at all).
4. Does the nested daemon work with `drop_capabilities = true` in the chosen runtime?
