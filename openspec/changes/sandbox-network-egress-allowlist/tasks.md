# Tasks

## 1. Configuration and validation

- [ ] 1.1 Add `allowed_domains` (None = not defined, list = defined) and `egress_proxy_image` to `AgentRunnerConfiguration` and read them in `AgentRunner.__load_configuration` (CLI value replaces the configuration-file completely; absent key and empty value are distinguished); verify with new testcases in `test_AgentRunner.py` for absent, empty, ini-only, CLI-only and CLI-overrides-ini
- [ ] 1.2 Implement `SandboxNetworkConfiguration` (mode unrestricted/allowlist/none, entry-validation: hostname-pattern, optional leading dot, no scheme/port/path/wildcard/IP, no redundant entry, `egress_proxy_image` required in mode allowlist); verify with testcases for every rejected case of the spec (error names the entry) and for the matching examples
- [ ] 1.3 Add the arguments `--alloweddomain` (repeatable) and `--egressproxyimage` to `scrais` in `Executables.py`; verify with the argument-testcase in `test_AgentRunner.py` and `scrais --help`
- [ ] 1.4 Document the two configuration keys and arguments in the tables of `RunAgentInSandbox.md` (including the difference between absent and empty `allowed_domains`); verify the tables are formatted consistently with the existing ones

## 2. Modes unrestricted and none

- [ ] 2.1 Add `--network none` for mode none and keep the current arguments unchanged for mode unrestricted in `AgentRunner.__run_sandbox`; verify with testcases on the generated docker command (mode unrestricted: command identical to the current one)
- [ ] 2.2 Print the start message for modes allowlist and none to stderr and nothing for mode unrestricted; verify with testcases capturing stderr
- [ ] 2.3 Write section "Network access" in `RunAgentInSandbox.md` (modes, absent versus empty allowlist, warning about `--mountdockersocket`, non-goals: no protection against exfiltration through an allowed domain); verify the documented example-configurations are accepted by the validation of 1.2

## 3. Egress-proxy

- [ ] 3.1 Implement the generation of the Squid configuration (D3); verify with a testcase which compares the generated configuration for a given allowlist
- [ ] 3.2 Implement `SandboxEgressProxy` (D6: network, proxy start, connect to bridge, docker arguments for the sandbox including proxy-variables and `--dns 127.0.0.1`, `stop()` removes proxy, network and temporary file); verify with testcases on mocked docker-calls, including that `stop()` runs when the sandbox start fails
- [ ] 3.3 Use `SandboxEgressProxy` in `AgentRunner.__run_sandbox` for mode allowlist and stop it in the existing `finally`-block; verify with testcases that the exit-code of the sandbox is returned and the cleanup happens on a non-zero exit-code
- [ ] 3.4 Show the denied requests from the proxy-log with `--verbose` (D7); verify with a testcase on a sample access-log
- [ ] 3.5 Choose a Squid-image with pinned tag which fulfills the image-contract (D2), determine the capabilities it needs, and document it plus the cleanup of leftover `scrais-`-resources in `RunAgentInSandbox.md`; verify by starting the documented image with a generated configuration

## 4. Integration checks

- [ ] 4.1 Run `scbuildcodeunits` for the repository and verify exit-code 0 without new linting-issues
- [ ] 4.2 Verify manually with a real sandbox in mode allowlist: allowed domain via HTTPS works; other domain, `http://`, other port, SSH, direct connection without proxy and external name resolution fail; this also with `drop_capabilities = false` and root in the sandbox; network and proxy are removed after the run
- [ ] 4.3 Verify manually that the assumption about the embedded DNS of docker (D4) holds on Windows with Docker Desktop and on Linux; otherwise switch to a fixed proxy-address as described in the risks and update design and tasks
- [ ] 4.4 Verify manually mode allowlist together with `-b true` and `dotnet restore` against a private package-source whose domain is allowed
- [ ] 4.5 Add the changelog entry; verify the entry names the new keys and arguments and states that configurations without allowlist are unchanged

## Workflow follow-up

- Reconcile the requirement "no new argument or configuration key" of the change `sandbox-nested-docker` with this change, whichever is archived second.
- Archive the change after the manual verifications are done.
