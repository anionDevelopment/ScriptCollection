# Agent Sandbox Docker Specification

## Purpose

Records how an agent in the agent sandbox (`scrais`) can use docker without weakening the sandbox.

## ADDED Requirements

### Requirement: Docker works normally inside the sandbox

When the prerequisites are met, the command `docker` inside the container SHALL work like on a normal machine for at least
`docker run`, `docker build`, `docker pull`, `docker ps` and `docker compose`, without additional arguments, environment
variables or manual preparation by the agent. No switch or configuration key SHALL be needed. The daemon SHALL be ready
before the initialization script and the agent start.

#### Scenario: Agent starts a container

- **WHEN** the agent executes `docker run --rm hello-world` in a sandbox whose prerequisites are met
- **THEN** the command succeeds and the container ran inside the sandbox

#### Scenario: Prerequisites are not met

- **WHEN** the host offers no suitable backend, the image contains no docker daemon, or the configured `drop_capabilities` makes the backend impossible
- **THEN** the sandbox starts without docker, `scrais` writes one line to stderr naming the missing prerequisite, and the container is not weakened in any way

### Requirement: Everything the agent starts stays inside the sandbox

The docker daemon used by the agent SHALL be private to the sandbox container. Containers, images, networks and volumes
which the agent creates SHALL NOT be visible on the daemon of the host and SHALL be gone when the sandbox ends. Containers
started by the agent SHALL NOT be able to access host files other than those the sandbox itself has mounted.

#### Scenario: Agent lists containers

- **WHEN** the agent executes `docker ps -a` in the sandbox
- **THEN** only containers of the private daemon are listed, never containers of the host

#### Scenario: Agent mounts a path into a nested container

- **WHEN** the agent starts a nested container with a bind mount of a path
- **THEN** the path is resolved inside the sandbox, so paths outside of the sandbox (for example the home folder of the host) cannot be reached

#### Scenario: Sandbox ends

- **WHEN** the sandbox container has ended
- **THEN** no container, image, network or volume of the agent remains on the host

### Requirement: No unsafe configuration is needed or used

For a run in which docker is provided, the `docker run` arguments of `scrais` SHALL NOT contain any argument which weakens
the isolation of the sandbox. The existing behavior of `drop_capabilities` SHALL stay as configured, unless the isolating
runtime makes a combination technically impossible; that case SHALL be rejected with a message instead of silently weakened.

#### Scenario: Start arguments are checked

- **WHEN** a testcase builds the `docker run` arguments for a run in which docker is provided
- **THEN** none of the forbidden arguments is contained, namely `--privileged`, a mount of the docker socket of the host,
  `--pid=host`, `--net=host`, `--ipc=host`, `--userns=host`, `--cap-add`, a security option which disables or relaxes
  seccomp, AppArmor or SELinux (for example `seccomp=unconfined`), and a `--device` of the host

### Requirement: The sandbox is never weakened to provide docker

`scrais` SHALL check before the start whether the host provides the isolation required for nested docker and whether the image
contains the docker daemon and CLI. If a check fails, `scrais` SHALL start the sandbox without docker (see above) and SHALL NOT
fall back to the host socket or to any weaker configuration to provide docker.

#### Scenario: Host has no suitable runtime

- **WHEN** the host does not offer the required isolating runtime
- **THEN** no docker daemon is started and no isolation-related argument is changed

#### Scenario: Image has no docker daemon

- **WHEN** the image does not contain the docker daemon
- **THEN** the sandbox starts without docker and the message names the image and the missing tool

### Requirement: The switch to mount the host docker socket is removed

The switch `-d`/`--mountdockersocket` SHALL NOT exist any more and SHALL NOT be replaced by another switch. `scrais` SHALL NOT
offer any way to mount the docker socket of the host into the sandbox. The warning about the host socket and the documentation
section about it SHALL be removed.

#### Scenario: Old switch is used

- **WHEN** `scrais` is started with `-d` or `--mountdockersocket`
- **THEN** argument parsing rejects it as an unknown argument

#### Scenario: Documentation

- **WHEN** a user reads `RunAgentInSandbox.md`
- **THEN** the section about the host docker socket is replaced by the section about docker in the sandbox, including prerequisites and limits

### Requirement: The rest of the command-line interface stays unchanged

Except for the removal of `-d`/`--mountdockersocket`, this change SHALL NOT add, remove or rename an argument of `scrais` and
SHALL NOT add a key to the configuration file. The names, short names, value formats and defaults of all other arguments SHALL stay as before.

#### Scenario: Argument list is compared

- **WHEN** the argument definitions of `scrais` before and after the change are compared
- **THEN** the only difference is the missing `-d`/`--mountdockersocket`

### Requirement: The feature works on Windows, macOS and Linux hosts

Docker in the sandbox SHALL work with the same command line and the same visible behavior on Windows, macOS and Linux hosts. The
host-specific part (which isolation backend is used) SHALL be selected by `scrais` per platform and SHALL NOT be visible in the
command line. Where a platform cannot provide a backend which fulfills the other requirements, docker SHALL be unavailable there (with the
message described above) instead of weakening the sandbox.

#### Scenario: Run on each platform

- **WHEN** `scrais` is used on a Windows, a macOS and a Linux host which meet the documented prerequisites
- **THEN** `docker run --rm hello-world` succeeds in the sandbox on all three

#### Scenario: Path handling

- **WHEN** the docker command is built on a Windows host
- **THEN** host paths are converted for the mounts in the same way as for the existing mounts

### Requirement: The feature is testable without docker

The decision logic (argument building, forbidden-argument check, prerequisite evaluation, entrypoint content) SHALL be separated
from process execution, so that testcases exercise it without docker and without a network.

#### Scenario: Prerequisite evaluation in a testcase

- **WHEN** a testcase covers the prerequisite check
- **THEN** the information about host runtimes and image content is supplied by a test double and no process is started
