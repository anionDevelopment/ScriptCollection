# Tasks

## 1. Configuration and validation

- [x] 1.1 Add `allowed_domains` (None = not defined, list = defined) and `egress_proxy_image` to `AgentRunnerConfiguration` and read them in `AgentRunner.__load_configuration` (allowlist from the section `AllowedDomains` whose values are comments; CLI value replaces the configuration-file completely; absent and empty section are distinguished); verify with new testcases in `test_AgentRunner.py` for absent, empty, ini-only with comments, duplicate entry, CLI-only and CLI-overrides-ini
- [x] 1.2 Implement `SandboxNetworkConfiguration` (mode unrestricted/allowlist/none, entry-validation: hostname-pattern, optional leading dot, no scheme/port/path/wildcard/IP, no redundant entry, `egress_proxy_image` required in mode allowlist); verify with testcases for every rejected case of the spec (error names the entry) and for the matching examples
- [x] 1.3 Add the arguments `--alloweddomain` (repeatable) and `--egressproxyimage` to `scrais` in `Executables.py`; verify with the argument-testcase in `test_AgentRunner.py` and `scrais --help`
- [x] 1.4 Document the two configuration keys and arguments in the tables of `RunAgentInSandbox.md` (including the comments and the difference between absent and empty section `AllowedDomains`); verify the tables are formatted consistently with the existing ones

## 2. Modes unrestricted and none

- [x] 2.1 Add `--network none` for mode none and keep the current arguments unchanged for mode unrestricted in `AgentRunner.__run_sandbox`; verify with testcases on the generated docker command (mode unrestricted: command identical to the current one)
- [x] 2.2 Print the start message for modes allowlist and none to stderr and nothing for mode unrestricted; verify with testcases capturing stderr
- [x] 2.3 Write section "Network access" in `RunAgentInSandbox.md` (modes, absent versus empty allowlist, warning about `--mountdockersocket`, non-goals: no protection against exfiltration through an allowed domain); verify the documented example-configurations are accepted by the validation of 1.2

## 3. Egress-proxy

- [x] 3.1 Implement the generation of the Squid configuration (D3); verify with a testcase which compares the generated configuration for a given allowlist
- [x] 3.2 Implement `SandboxEgressProxy` (D6: network, proxy start, connect to bridge, docker arguments for the sandbox including proxy-variables and `--dns 127.0.0.1`, `stop()` removes proxy, network and temporary file); verify with testcases on mocked docker-calls, including that `stop()` runs when the sandbox start fails
- [x] 3.3 Use `SandboxEgressProxy` in `AgentRunner.__run_sandbox` for mode allowlist and stop it in the existing `finally`-block; verify with testcases that the exit-code of the sandbox is returned and the cleanup happens on a non-zero exit-code
- [x] 3.4 Show the denied requests from the proxy-log with `--verbose` (D7); verify with a testcase on a sample access-log
- [x] 3.5 Choose a Squid-image with pinned tag which fulfills the image-contract (D2), determine the capabilities it needs, and document it plus the cleanup of leftover `scrais-`-resources in `RunAgentInSandbox.md`; verify by starting the documented image with a generated configuration

## 4. Integration checks

- [x] 4.1 Run `scbuildcodeunits` for the repository and verify exit-code 0 without new linting-issues
- [x] 4.2 Verify manually with a real sandbox in mode allowlist: allowed domain via HTTPS works; other domain, `http://`, other port, SSH, direct connection without proxy and external name resolution fail; this also with `drop_capabilities = false` and root in the sandbox; network and proxy are removed after the run
- [x] 4.3 Verify manually that the assumption about the embedded DNS of docker (D4) holds on Windows with Docker Desktop; otherwise switch to a fixed proxy-address as described in the risks and update design and tasks (a Linux-host with docker engine is expected to behave the same, because Docker Desktop runs the same docker-daemon in a Linux-VM, but it is not tested)
- [x] 4.4 Verify manually mode allowlist together with `-b true` and `dotnet restore` against a private package-source whose domain is allowed
- [x] 4.5 Add the changelog entry; verify the entry names the new keys and arguments and states that configurations without allowlist are unchanged

Results of the verification on 2026-11-06 (Docker Desktop 29.9.2 on Windows, proxy `ubuntu/squid:7.2-26.04_edge`):

- 3.5: Squid runs as `_daemon_` and needs no capability; the proxy is started with `--cap-drop all` and `--security-opt no-new-privileges:true`. The output of Squid does not reach `docker logs` (pebble), so the access-log is written to a file and read with `docker exec` (D7 updated).
- 4.2: Checked from containers of `aniondev/scbuilder:v1.2.19` with the docker-arguments of `SandboxEgressProxy`, once with `--cap-drop all` and once as root with the default capabilities: exact host, domain with leading dot and its subdomain are reachable; other domain, `example.com.evil.org`, `http://`, port 8443, direct connections without proxy (port 443 and 22) and external name resolution fail; network and proxy are removed after the run.
- 4.3: Holds on Windows with Docker Desktop (proxy-name resolved, external names not). Not tested on a Linux-host with docker engine (user decision); the same behavior is expected because Docker Desktop runs the same docker-daemon with the same embedded DNS in a Linux-VM. If it differs, the sandbox can not reach the proxy and every request fails (fail-closed, the internal network has no route to the outside).
- 4.4: `AgentRunner.run` with `-b true` and the allowlist `projects.aniondev.de, api.nuget.org` restored `CCOTLibrary` from the private package-source (with an image derived from `aniondev/scbuilder:v1.2.19` with ScriptCollection 4.4.69, because the published SCBuilder-images contain ScriptCollection 4.4.66 without `scregisterpackagesources`). Without `projects.aniondev.de` in the allowlist the restore failed with 403 from the proxy and the exit-code 1 was returned.

## Workflow follow-up

- Done: reconciled the requirement "no new argument or configuration key" of the change `sandbox-nested-docker` with this change (2026-11-06, the requirement there is now limited to docker itself and keeps the arguments and keys of this change; the interplay with the allowlist is a requirement of `sandbox-nested-docker`).
- Archive the change after the manual verifications are done.
