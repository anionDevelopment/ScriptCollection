# Agent Sandbox Status Reporting Specification

## Purpose

Records how the state of an agent which runs in the agent sandbox (`scrais`) becomes visible in herdr, and which isolation rules the channel between container and host has to respect.

## ADDED Requirements

### Requirement: The state of a sandboxed agent is reported to herdr

When `scrais` is started inside a herdr pane (herdr environment variables are present) and the used coding-agent has a status adapter, `scrais` SHALL report the state of the agent to herdr through the herdr CLI. The reported states SHALL be `working` while the agent processes a prompt, `idle` while it waits for input, and `blocked` while it waits for a decision of the user.
When the container ends, `scrais` SHALL release the agent in herdr.

#### Scenario: Agent receives a prompt

- **WHEN** the agent starts to process a prompt in the container
- **THEN** herdr is informed that the agent is `working`

#### Scenario: Agent finished a turn

- **WHEN** the agent has finished a turn and waits for input
- **THEN** herdr is informed that the agent is `idle`

#### Scenario: Agent needs a decision

- **WHEN** the agent asks the user for a decision or approval
- **THEN** herdr is informed that the agent is `blocked`

#### Scenario: Container ends

- **WHEN** the container has ended for any reason (agent finished, user quit, error)
- **THEN** `scrais` releases the agent in herdr before it returns

#### Scenario: Start state

- **WHEN** the container starts
- **THEN** the state is `working` if a prompt was given and `idle` otherwise, until the first event of the agent arrives

### Requirement: Reporting is inactive outside of herdr and for agents without adapter

`scrais` SHALL NOT call herdr when the herdr environment variables are not present, and SHALL NOT report for a coding-agent without status adapter.
In both cases the agent SHALL be started exactly as without this feature.

#### Scenario: scrais is started outside of herdr

- **WHEN** `HERDR_ENV` is not `1` or the pane id or herdr binary path is missing
- **THEN** no herdr command is executed and no additional mount is added to the container

#### Scenario: Agent without adapter

- **WHEN** the coding-agent is copilot or vibe
- **THEN** no status is reported and the user is informed once in verbose output that this agent has no status adapter

### Requirement: The container can only communicate fixed state tokens to the host

The channel from container to host SHALL consist of one event file in a dedicated host folder which is mounted into the container.
The host SHALL accept only the exact tokens `working`, `idle`, `blocked` and `ended` from it, SHALL ignore every other line, and SHALL NOT pass any content of the file as argument, message or command to herdr except the validated state.
The herdr socket, the herdr binary and the herdr environment variables SHALL NOT be made available inside the container.

#### Scenario: Container writes an unknown or malicious line

- **WHEN** the event file contains a line which is not an accepted token (for example shell syntax or a path)
- **THEN** the line is ignored and nothing is passed to herdr

#### Scenario: herdr is unavailable or a report fails

- **WHEN** the herdr CLI fails or does not answer within its timeout
- **THEN** the failure is shown in verbose output only, the agent keeps running, and later events are still reported

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
The hook helper which runs in the container SHALL be a Linux shell script written with LF line endings and started via `sh`, independent of the host platform.
Mounts SHALL use the same path conversion as the existing mounts, and the herdr call SHALL use `HERDR_BIN_PATH` as given, as an argument list without shell, so that `.exe` paths and spaces work.

#### Scenario: Windows host

- **WHEN** `scrais` runs on a Windows host inside herdr
- **THEN** the event folder is mounted with a converted path, the helper script has LF line endings, and herdr is called through the executable named by `HERDR_BIN_PATH`

#### Scenario: macOS and Linux host

- **WHEN** `scrais` runs on a macOS or Linux host inside herdr
- **THEN** the same states are reported as on Windows

### Requirement: The feature is testable without herdr, docker or a server

The logic (token validation, event reading, mapping, command building, adapter content) SHALL be separated from process start and file-system watching, so that testcases exercise it without herdr, docker or a network.

#### Scenario: Testcase for the relay

- **WHEN** a testcase covers the relay
- **THEN** the herdr reporter is replaced by a recording test double and no process is started
