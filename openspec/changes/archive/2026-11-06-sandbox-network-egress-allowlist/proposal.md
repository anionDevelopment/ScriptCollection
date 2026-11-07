# Proposal

## Why

The agent in the sandbox of `scrais` has unrestricted network access today: the container is attached to the default bridge network of docker and can reach every host on every port.
Since the sandbox can get the build-environment (see capability `agent-sandbox-build-environment`), the agent can hold secrets like the credentials of private package-sources.
A manipulated or misbehaving agent can send them anywhere. Restricting the outgoing traffic to a small list of known HTTPS-domains is the most effective protection against this exfiltration.

## What Changes

- New: an optional allowlist of domains (section `AllowedDomains` in `AgentSandboxConfiguration.ini` with one entry per domain whose value is an optional comment, CLI argument which overrides it).
- Without an allowlist the network access stays unrestricted exactly as today (no behavior change for existing configurations).
- When an allowlist is defined, everything else is blocked: only the listed domains are reachable, and only via HTTPS (port 443). A defined but empty allowlist (empty section) blocks all network access.
- New: an entry `example.com` allows exactly this host; an entry `.example.com` allows the domain and all its subdomains.
- New: the allowlist is enforced outside of the sandbox container by an egress-proxy (sidecar container from a pinned Squid-image, configured by `egress_proxy_image`). The sandbox container itself has no route to the outside, so the restriction cannot be lifted from inside the sandbox and no capability is needed.
- New: in restricted mode `scrais` prints the effective restriction at start, so a failing connection of the agent can be traced back to the configuration.
- New: with `--verbose` the requests denied by the egress-proxy are shown after the run, so the user can find out which domains a tool needs.
- `RunAgentInSandbox.md` documents the allowlist, the configuration keys and example allowlists. Changelog entry.

## Capabilities

### New Capabilities

- `agent-sandbox-network-access`: which network connections the agent in the sandbox can establish, how a restriction is configured and how it is enforced.

### Modified Capabilities

- `agent-sandbox-status-reporting`: the requirement "The command-line interface of scrais stays unchanged" was written for the change which introduced the status reporting ("This change SHALL NOT add ... an argument"), but as a requirement of the main spec it forbids every new argument of `scrais`. It is restated as what it means: the status reporting itself needs no argument and no key.

## Impact

- `AgentRunner.py` (configuration, docker arguments, lifecycle of network and proxy), new module for the egress-proxy, `Executables.py` (new arguments of `scrais`), `RunAgentInSandbox.md`, changelog.
- New external dependency at runtime: a Squid-image with pinned tag, declared by the user (image-name from `ImageDefinition.csv` of the repository or image-address including tag). It is only needed when the allowlist contains at least one domain.
- Existing configurations are not affected.
- In restricted mode tools inside the sandbox must use the proxy (environment-variables `HTTPS_PROXY`/`HTTP_PROXY`). Tools which ignore them cannot connect. Non-HTTPS protocols (for example git via SSH) do not work in restricted mode.
- The active change `sandbox-nested-docker` requires that `scrais` gets no new argument or configuration key apart from its own removal. The change which is archived second has to reconcile this requirement. Nested containers and a nested docker daemon are subject to the same restriction and need the proxy-configuration too.
- The status-reporting to herdr is file-based (volume) and is not affected.
