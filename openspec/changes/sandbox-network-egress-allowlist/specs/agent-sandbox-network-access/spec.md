# Spec Delta

## Purpose

Defines which network connections the agent in the sandbox of `scrais` can establish, how an allowlist restricts them and that the restriction is enforced outside of the reach of the agent, so secrets in the sandbox cannot be sent to arbitrary destinations.

## ADDED Requirements

### Requirement: Network access is unrestricted without allowlist
When no allowlist is defined, the sandbox SHALL have the same unrestricted network access as before the allowlist existed, and `scrais` SHALL NOT start any additional container or network.

#### Scenario: No allowlist defined
- **WHEN** `scrais` is started for a repository whose `AgentSandboxConfiguration.ini` contains no `allowed_domains` and no allowlist is given on the command-line
- **THEN** the sandbox can connect to every host and no proxy container and no network are created

### Requirement: Defined allowlist blocks everything else
When an allowlist is defined, the sandbox SHALL be able to connect only to the allowed domains, only on port 443 and only through the proxy which is announced in the sandbox. Every other connection to the outside SHALL fail. A defined allowlist without any domain SHALL block all connections to the outside.

#### Scenario: Allowed domain via HTTPS
- **WHEN** the allowlist contains `api.example.com` and a tool in the sandbox requests `https://api.example.com/` using the announced proxy
- **THEN** the request reaches `api.example.com`

#### Scenario: Domain not in the allowlist
- **WHEN** a tool in the sandbox requests `https://other.example.org/` using the announced proxy
- **THEN** the request is denied

#### Scenario: Other port or protocol
- **WHEN** a tool in the sandbox requests `http://api.example.com/` or `https://api.example.com:8443/` or connects to `api.example.com` via SSH
- **THEN** the connection is not established

#### Scenario: Tool ignores the proxy
- **WHEN** a tool in the sandbox tries to connect directly to any host outside of the sandbox without using the announced proxy
- **THEN** the connection is not established

#### Scenario: Empty allowlist
- **WHEN** the configuration-file contains `allowed_domains =` without any entry
- **THEN** every attempt of the agent to connect to a host outside of the sandbox fails

### Requirement: Domain entries match exactly or including subdomains
An allowlist entry without leading dot SHALL match exactly this host. An entry with leading dot SHALL match the domain itself and all of its subdomains.

#### Scenario: Exact entry
- **WHEN** the allowlist contains `example.com`
- **THEN** `example.com` is allowed and `api.example.com` is denied

#### Scenario: Entry with leading dot
- **WHEN** the allowlist contains `.example.com`
- **THEN** `example.com`, `api.example.com` and `a.b.example.com` are allowed and `example.com.evil.org` is denied

### Requirement: Invalid allowlist entries are rejected
`scrais` SHALL reject the start with an error message which names the entry when an allowlist entry is not a valid hostname (optionally with leading dot), contains a scheme, a port, a path or a wildcard, is an IP-address, or is already covered by another entry.

#### Scenario: Entry with scheme
- **WHEN** the allowlist contains `https://example.com`
- **THEN** `scrais` exits with an error naming `https://example.com` before a container is started

#### Scenario: Redundant entry
- **WHEN** the allowlist contains `.example.com` and `api.example.com`
- **THEN** `scrais` exits with an error naming `api.example.com` as covered by `.example.com` before a container is started

### Requirement: Allowlist via configuration-file and command-line
The allowlist SHALL be definable in `AgentSandboxConfiguration.ini` and via a command-line argument of `scrais`. An allowlist given on the command-line SHALL replace the allowlist of the configuration-file completely.

#### Scenario: Command-line replaces the allowlist
- **WHEN** the configuration-file defines `allowed_domains = a.example.com` and the command-line gives the domain `b.example.com`
- **THEN** only `b.example.com` is allowed

#### Scenario: Allowlist only on the command-line
- **WHEN** the configuration-file defines no `allowed_domains` and the command-line gives the domain `b.example.com`
- **THEN** only `b.example.com` is allowed

### Requirement: Restriction cannot be lifted from inside the sandbox
The network restriction SHALL be enforced outside of the sandbox container and SHALL NOT require any capability in the sandbox container. In restricted mode the sandbox container SHALL NOT be able to resolve external host names itself.

#### Scenario: Agent with root-rights in the sandbox
- **WHEN** the agent runs as root in the sandbox (also with `drop_capabilities = false`) and tries to change routes, firewall-rules or proxy-settings
- **THEN** it still cannot connect to a host which is not allowed

#### Scenario: Name resolution in the sandbox
- **WHEN** a tool in the sandbox resolves the name of an external host in restricted mode
- **THEN** the resolution fails

### Requirement: Egress-proxy image must be configured for a non-empty allowlist
When the allowlist contains at least one domain, `scrais` SHALL require the configuration `egress_proxy_image` (image-name from the image-definition-file of the repository or image-address including tag) and SHALL reject the start with an error message when it is missing.

#### Scenario: Missing egress-proxy image
- **WHEN** the allowlist contains `example.com` and `egress_proxy_image` is neither configured nor given on the command-line
- **THEN** `scrais` exits with an error naming `egress_proxy_image` before a container is started

### Requirement: Restriction is shown at start
In restricted mode `scrais` SHALL print the effective restriction before the agent starts.

#### Scenario: Restricted mode
- **WHEN** `scrais` starts with the allowlist `api.example.com,.example.org`
- **THEN** the output states that network access is restricted to `api.example.com` and `.example.org` via HTTPS

#### Scenario: Empty allowlist
- **WHEN** `scrais` starts with a defined but empty allowlist
- **THEN** the output states that the sandbox has no network access

### Requirement: Network resources are removed after the run
All network resources which `scrais` creates for one run (network, proxy container) SHALL be removed when the run ends, also when the agent or the start of the sandbox fails.

#### Scenario: Agent fails
- **WHEN** the sandbox exits with a non-zero exit-code in restricted mode
- **THEN** the proxy container and the network of this run do not exist anymore and the exit-code of the sandbox is returned

### Requirement: Denied requests are shown in verbose mode
In restricted mode with `--verbose`, `scrais` SHALL show the requests which were denied by the egress-proxy after the run.

#### Scenario: Denied request with verbose
- **WHEN** a tool requested `https://other.example.org/` during a run with `--verbose` and the domain is not allowed
- **THEN** the output after the run lists the denied request to `other.example.org`
