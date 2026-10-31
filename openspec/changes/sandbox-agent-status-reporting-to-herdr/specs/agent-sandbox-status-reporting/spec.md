# Agent Sandbox Status Reporting Specification

## Purpose

Records how the state of an agent which runs in the agent sandbox (`scrais`) becomes visible in herdr, which prerequisite the image has to fulfill, and which isolation rules the channel between container and host has to respect.

## ADDED Requirements

### Requirement: The state of a sandboxed agent is reported to herdr

When `scrais` is started inside a herdr pane (herdr environment variables are present) and the image fulfills the status prerequisite, `scrais` SHALL report the state of the agent to herdr through the herdr CLI.
This SHALL apply to all coding-agents of `scrais`: claude, copilot, codex, vibe and opencode.
The reported states SHALL be `working` while the agent processes a prompt, `idle` while it waits for input, and `blocked` while it waits for a decision of the user.

#### Scenario: Agent receives a prompt

- **WHEN** the agent starts to process a prompt in the container
- **THEN** herdr is informed that the agent is `working`

#### Scenario: Agent finished a turn

- **WHEN** the agent has finished a turn and waits for input
- **THEN** herdr is informed that the agent is `idle`

#### Scenario: Agent needs a decision

- **WHEN** the agent asks the user for a decision or approval
- **THEN** herdr is informed that the agent is `blocked`

#### Scenario: Agent continues after a decision

- **WHEN** the agent continues its work after it was `blocked`
- **THEN** herdr is informed that the agent is `working`

#### Scenario: Start state

- **WHEN** the container starts and the image provides the status helper
- **THEN** the state is `working` if a prompt was given and `idle` otherwise, until the first event of the agent arrives

#### Scenario: Agent has no event for a state

- **WHEN** a coding-agent offers no event from which a state can be derived (for example vibe has no event for an approval request)
- **THEN** that state is not reported, the last reported state stays, and the limit is documented for that agent

### Requirement: The agent is released when the container ends

When the container ends and at least one state was reported, `scrais` SHALL release the agent in herdr.

#### Scenario: Container ends

- **WHEN** the container has ended for any reason (agent finished, user quit, error) and a state was reported before
- **THEN** `scrais` releases the agent in herdr before it returns

### Requirement: All agents are handled on the same way

`scrais` SHALL handle every coding-agent on the same way.
The status code of `scrais` SHALL NOT contain a branch, adapter, registry entry, mount, argument or other structure for a single coding-agent.
The coding-agent SHALL only appear as a value in the agent name of the report.
Differences between the agents SHALL be limited to the hook configuration inside the image, and every hook configuration SHALL report through the same status helper.

#### Scenario: Container start is compared across agents

- **WHEN** the status-related docker arguments and entrypoint lines are compared for all coding-agents
- **THEN** they are identical

#### Scenario: Report is compared across agents

- **WHEN** the same event is processed for different coding-agents
- **THEN** the herdr commands only differ in the value of the agent name

### Requirement: The image declares status support through a defined prerequisite

An image supports the status report if it fulfills both of the following conditions:
It SHALL provide the executable `scrais-agent-status` on the `PATH`, and it SHALL contain a user-level hook configuration of its agents which calls this executable with a state token.
`RunAgentInSandbox.md` SHALL document this prerequisite.

#### Scenario: Image fulfills the prerequisite

- **WHEN** an image fulfills the prerequisite and `scrais` runs inside herdr
- **THEN** the status report works

#### Scenario: Image does not fulfill the prerequisite

- **WHEN** an image does not provide the status helper
- **THEN** no state is reported, no herdr command is executed, and the user is informed once in verbose output that no status was received

### Requirement: The status helper can not influence the agent

`scrais-agent-status` SHALL append its token to the event file if the event folder exists and SHALL do nothing otherwise.
It SHALL always exit with code 0 and SHALL NOT write to stdout.

#### Scenario: Image with status support runs outside of herdr

- **WHEN** an image with status support is used without the event folder
- **THEN** the status helper does nothing and the agent runs as usual

#### Scenario: Event file can not be written

- **WHEN** the status helper can not append to the event file
- **THEN** it exits with code 0 and writes nothing to stdout

### Requirement: Running the agent never depends on the status report

The agent SHALL start and run independent of herdr, of the status support of the image and of any failure of the status report.
The exit code of `scrais` SHALL be the same as without this feature.

#### Scenario: scrais is started outside of herdr

- **WHEN** `HERDR_ENV` is not `1` or the pane id or herdr binary path is missing
- **THEN** no herdr command is executed, no additional mount is added to the container, and the entrypoint is the same as without this feature

#### Scenario: Image without status support

- **WHEN** `scrais` runs inside herdr with an image without status helper
- **THEN** the agent starts and runs as usual

#### Scenario: Status report fails on the host

- **WHEN** the event channel can not be created or the relay fails
- **THEN** the failure is shown in verbose output only, and the agent starts or keeps running

#### Scenario: herdr is unavailable or a report fails

- **WHEN** the herdr CLI fails or does not answer within its timeout
- **THEN** the failure is shown in verbose output only, the agent keeps running, and later events are still reported

### Requirement: The container can only communicate fixed state tokens to the host

The channel from container to host SHALL consist of one event file in a dedicated host folder which is mounted into the container.
The host SHALL accept only the exact tokens `working`, `idle` and `blocked` from it, SHALL ignore every other line, and SHALL NOT pass any content of the file as argument, message or command to herdr except the validated state.
The herdr socket, the herdr binary and the herdr environment variables SHALL NOT be made available inside the container.

#### Scenario: Container writes an unknown or malicious line

- **WHEN** the event file contains a line which is not an accepted token (for example shell syntax or a path)
- **THEN** the line is ignored and nothing is passed to herdr

### Requirement: Reports are ordered and attributable

Every report SHALL use a stable source identifier owned by `scrais` and an agent name which differs from the names of the agents which herdr supports natively.
Every report SHALL carry a sequence number which increases across runs.

#### Scenario: Two reports in quick succession

- **WHEN** two events arrive within a short time
- **THEN** the second report has a higher sequence number than the first, so herdr does not discard it

### Requirement: The command-line interface of scrais stays unchanged

This change SHALL NOT add, remove or rename an argument of `scrais` and SHALL NOT add a key to the configuration file.
The reporting is active automatically when the herdr environment variables are present.

#### Scenario: Argument list is compared

- **WHEN** the argument definitions of `scrais` before and after the change are compared
- **THEN** names, short names, actions and defaults are identical

### Requirement: Reporting works on Windows, macOS and Linux hosts

Reporting SHALL work on Windows, macOS and Linux hosts with identical behavior.
The container user SHALL be able to write the event file independent of the user of the host.
Mounts SHALL use the same path conversion as the existing mounts, and the herdr call SHALL use `HERDR_BIN_PATH` as given, as an argument list without shell, so that `.exe` paths and spaces work.

#### Scenario: Windows host

- **WHEN** `scrais` runs on a Windows host inside herdr
- **THEN** the event folder is mounted with a converted path, and herdr is called through the executable named by `HERDR_BIN_PATH`

#### Scenario: macOS and Linux host

- **WHEN** `scrais` runs on a macOS or Linux host inside herdr
- **THEN** the same states are reported as on Windows

#### Scenario: Container user differs from host user

- **WHEN** the user of the container has another user id than the user of the host
- **THEN** the container user can append to the event file

### Requirement: The feature is testable without herdr, docker or a server

The logic (token validation, event reading, command building, generation of the status-related container arguments) SHALL be separated from process start and file-system watching, so that testcases exercise it without herdr, docker or a network.

#### Scenario: Testcase for the relay

- **WHEN** a testcase covers the relay
- **THEN** the herdr reporter is replaced by a recording test double and no process is started
