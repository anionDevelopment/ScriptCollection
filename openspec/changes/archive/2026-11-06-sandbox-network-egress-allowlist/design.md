# Design

## Context

See proposal.md - Why. Current state (verified in the code): `AgentRunner.__run_sandbox` starts the sandbox with `docker run --rm ...` without any `--network` argument, so the container is attached to the default bridge network. `drop_capabilities` only adds `--cap-drop all` and `no-new-privileges`. The configuration is loaded in `AgentRunner.__load_configuration`: `codingagent`, `image`, `drop_capabilities` are required, `provide_build_environment` is optional (opt-in). The image of the sandbox is resolved by `__get_image_to_use` (image-name from `ImageDefinition.csv` of the repository or image-address including tag).

Docker has no built-in egress filtering by domain. Domain-based filtering therefore needs a component which sees the host name of a connection.

## Goals / Non-Goals

**Goals:**
- Three network modes as defined in the spec: unrestricted (no allowlist defined, default, unchanged behavior), allowlist (allowlist with domains), none (allowlist defined but empty).
- Enforcement outside of the sandbox container without any capability in the sandbox.
- No interception of TLS (no own CA, no changes in the image of the sandbox).
- Same on Windows, macOS and Linux hosts, using only docker features which exist on all of them.

**Non-Goals:**
- Filtering by path or content of requests (only the host name is checked).
- Protection against exfiltration through an allowed domain (for example uploading secrets into a repository on an allowed git-host). The allowlist limits the destinations, not what is sent there.
- Restricting `--mountdockersocket`: whoever has the socket of the host can start a container with unrestricted network. The existing warning stays the only measure.
- Waiting for or retrying connections.

## Decisions

### D1: Egress-proxy as sidecar on an internal docker network

Per run, `scrais` creates a docker network with `docker network create --internal scrais-<run-id>`. An internal network has no route to the outside. The proxy container is started in this network and is additionally connected to the default bridge network (`docker network connect bridge <proxy>`), so only the proxy can reach the outside. The sandbox container is started with `--network scrais-<run-id>` and gets `HTTPS_PROXY`, `HTTP_PROXY`, `https_proxy` and `http_proxy` set to `http://scrais-proxy-<run-id>:3128` (both spellings because tools differ in which one they read).

Alternatives:
- iptables/ipset inside the sandbox container (like the devcontainer-firewall of Claude Code): needs `NET_ADMIN`, which contradicts `drop_capabilities`, rules are based on IP-addresses which change for CDNs, and root in the container can remove the rules. Rejected.
- Firewall on the host: platform-specific (Windows, macOS with Docker Desktop VM, Linux) and changes the host. Rejected.
- Proxy as process on the host: an internal network cannot reach the host, and opening it would also open other host-services. Rejected.

### D2: Squid as proxy, image pinned by the user

Squid is a mature proxy with domain-ACLs; no security-critical proxy code is maintained in ScriptCollection. The image is configured by the new key `egress_proxy_image` and is resolved with the same function as `image` (`__get_image_to_use`), so the pinned tag lives in `ImageDefinition.csv` of the repository or in the configuration, and custom registries from `ImageRegistries.csv` work as for the sandbox image. ScriptCollection itself does not hardcode an image tag, so no ScriptCollection-release is needed to update Squid.

Contract for the image (documented): its default command starts Squid in the foreground with the configuration `/etc/squid/squid.conf`. `scrais` mounts the generated configuration read-only at this path. The documentation names a concrete image with pinned tag which fulfills the contract (to be chosen and verified in the tasks).

Alternative: own proxy command in ScriptCollection which runs in a sidecar from the sandbox image. No extra image, but security-critical code of our own. Rejected by the user.

### D3: Generated Squid configuration

The configuration is generated per run and contains only what is needed:

- `http_port 3128`
- `acl allowed_domains dstdomain -n <entries>`: `dstdomain` uses the same syntax as the allowlist (leading dot includes subdomains). `-n` disables reverse-DNS-lookups, so a CONNECT to an IP-address never matches through its reverse name (secondary source: Squid documentation, to be verified).
- `acl https_port port 443`
- `http_access deny !CONNECT` (no plain HTTP, no HTTP-requests through the proxy)
- `http_access deny CONNECT !https_port`
- `http_access allow CONNECT allowed_domains`
- `http_access deny all`
- `cache deny all`, unbuffered access-log to `/var/log/squid/access.log` in the proxy-container (used for D7), `pinger_enable off` (the pinger needs `NET_RAW`, see D6), no other features.

TLS is tunneled (CONNECT) and not intercepted, so the trusted root-CAs of the build-environment keep working unchanged.

### D4: Network modes and their docker arguments

| Mode | Condition | Docker arguments of the sandbox | Proxy |
| --- | --- | --- | --- |
| unrestricted | no allowlist defined (no section `AllowedDomains` and no `--alloweddomain`) | none (default bridge as today) | no |
| allowlist | allowlist defined with at least one domain | `--network scrais-<run-id>`, proxy-variables, `--dns 127.0.0.1` | yes |
| none | allowlist defined without domain (empty section `AllowedDomains`) | `--network none` | no |

Mode "none" needs neither network nor proxy nor `egress_proxy_image`. `--dns 127.0.0.1` makes external name resolution in the sandbox fail (nothing listens there), while the embedded DNS of docker still resolves the name of the proxy container (assumption: the embedded DNS answers container names itself and forwards only other names to the configured server; to be verified). This closes DNS as exfiltration channel. The proxy resolves names itself.

### D5: Configuration

- Section `AllowedDomains`: optional, one entry per domain (`<domain> = <comment>`). The value is a comment for the reader of the file (for example why the domain is needed), may be empty and does not influence the behavior. A comment as value and not as `#`-line is chosen because it belongs to exactly one entry. An own section and not a comma-separated key is chosen because every entry needs its own line for its comment; a domain listed twice is then rejected by the parser of the ini-file. Absent section means "no allowlist defined" (mode unrestricted); empty section means "allowlist without domain" (mode none). The difference between absent and empty is intended and documented. The key needs the `=` (also without comment), because the parser does not allow keys without value. CLI: `--alloweddomain <entry>`, repeatable; if given at least once, it replaces the list of the configuration-file completely. There is deliberately no CLI-argument to remove an allowlist of the configuration-file for one run (not requested; it would make it too easy to bypass a restriction which was configured on purpose).
- `egress_proxy_image`: required only in mode allowlist. CLI: `--egressproxyimage`.
- There is no key for unrestricted access: unrestricted is simply the absence of an allowlist.
- Validation before any container or network is created: every entry must match a hostname-pattern (labels of letters, digits and hyphens, at least two labels, optional leading dot), must not be an IP-address and must not be covered by another entry (`api.example.com` is covered by `.example.com`; `example.com` is covered by `.example.com`). Rejecting redundant entries also avoids that Squid refuses or warns about overlapping `dstdomain`-entries.

The values are added to `AgentRunnerConfiguration`; the validation is part of a new class `SandboxNetworkConfiguration` (mode, entries) so `__load_configuration` only reads values and does not grow further.

### D6: Lifecycle in a new class

A new class `SandboxEgressProxy` in its own module (for example `ScriptCollection/AgentSandbox/SandboxEgressProxy.py` next to the existing structure; final location in the tasks) owns network and proxy of one run: generate the configuration into a temporary file, create the network, start the proxy (`docker run -d --rm --name scrais-proxy-<run-id> --network scrais-<run-id> --volume <conf>:/etc/squid/squid.conf:ro <image>`), connect it to the bridge network, return the docker arguments for the sandbox, and remove proxy, network and temporary file in `stop()`. `AgentRunner.__run_sandbox` calls `stop()` in its existing `finally`-block. `<run-id>` is a random uuid, so parallel runs do not collide.

If `scrais` is killed hard, network and proxy can remain. They are recognizable by the prefix `scrais-` and the documentation explains how to remove them. There is no automatic cleanup of other runs, because a parallel run could still use them.

There is no readiness-wait for Squid (no wait-loop, see behavior-rules). The sandbox is started after the proxy container was started; the initialization of the sandbox (entrypoint, initialization-script, agent start) usually takes longer than the start of Squid. If a tool connects earlier it gets a connection error. This is documented as risk.

### D7: Denied requests in verbose mode

Before the proxy is removed, `scrais` reads the access-log of the proxy with `docker exec <proxy> cat /var/log/squid/access.log` when `--verbose` is set and prints the denied entries (`TCP_DENIED`) with their host to stderr. Without `--verbose` nothing is printed. `docker logs` was planned first, but the verification showed that `ubuntu/squid` runs Squid under the service-manager pebble, which does not forward the output of Squid to `docker logs`.

### D8: Start message

Printed to stderr before the sandbox starts in modes allowlist and none, one line: `Network access of the sandbox is restricted to <entries> via HTTPS.` / `The sandbox has no network access.` In mode unrestricted nothing is printed, so the output stays as before.

## Risks / Trade-offs

- [Absent versus empty] An empty section `AllowedDomains` (block all) and a missing section (unrestricted) look similar. → Documented explicitly; the start message makes the effective mode visible.
- [Domains of the agents are unknown] The coding-agents and package-managers may need more domains than expected (login, telemetry, CDNs). → Verbose output of denied requests (D7); documentation contains example lists marked as to be verified by the user.
- [Proxy-unaware tools] Tools which ignore the proxy-variables cannot connect. → Fail-closed is intended; documented.
- [Start order] A connection before Squid listens fails. → Documented; no wait-loop by rule. If this turns out to be a problem in practice, a bounded readiness-check is a separate decision of the user.
- [Embedded DNS behavior] Assumption in D4 about the embedded DNS of docker on internal networks. → Verified on Windows with Docker Desktop, not tested on a Linux-host with docker engine; if it does not hold there, the sandbox can not reach the proxy (fail-closed) and the proxy is addressed by a fixed IP-address in a dedicated subnet instead.
- [Squid as root] The proxy container needs to drop privileges to the Squid user. → Verified: Squid runs as `_daemon_` in the chosen image and needs no capability; the proxy container is started with `--cap-drop all` and `--security-opt no-new-privileges:true`.
- [Leftover resources after hard kill] → Prefix `scrais-` and documented cleanup command.
- [Conflict with `sandbox-nested-docker`] Its spec forbids new arguments/keys of `scrais`. → Whichever change is archived second reconciles the requirement; nested docker daemons need the proxy-variables for pulls.

## Migration Plan

1. Release with changelog entry. Existing configurations keep working unchanged.
2. Users who want the restriction add the section `AllowedDomains` plus `egress_proxy_image = ...` (and the image to `ImageDefinition.csv`) to `AgentSandboxConfiguration.ini`.
3. Rollback: removing the section `AllowedDomains` restores the unrestricted behavior without downgrading ScriptCollection.

## Decisions made during the implementation

- Verification with real docker (Docker Desktop 29.9.2 on Windows, sandbox-image `aniondev/scbuilder:v1.2.19`, see tasks 3.5, 4.2 and 4.3): Squid runs in `ubuntu/squid:7.2-26.04_edge` as the unprivileged user `_daemon_` and needs no capability, so the proxy-container is started with `--cap-drop all` and `--security-opt no-new-privileges:true` (the pinger, which would need `NET_RAW`, is disabled). The assumption about the embedded DNS of docker (D4) holds on Windows with Docker Desktop: the name of the proxy-container is resolved, external names are not. A Linux-host with docker engine was not tested (user decision); the same behavior is expected because Docker Desktop runs the same docker-daemon in a Linux-VM, and a deviation would fail closed (see the risk about the embedded DNS).
- Image: `ubuntu/squid:7.2-26.04_edge` (Canonical). It is the highest Squid-version and the only one on a supported Ubuntu-LTS-base (26.04); the 6.13-tags are based on Ubuntu 25.04, which is out of support. All tags of this repository are channel-tags which are rebuilt (also `_beta`); a digest is not used because `ImageDefinition.csv` pins by tag. The image is declared as `Squid` in `ImageDefinition.csv`, and `scbuildcodeunits` sets `egress_proxy_image` from it like it sets `image` from `SCBuilder`.
