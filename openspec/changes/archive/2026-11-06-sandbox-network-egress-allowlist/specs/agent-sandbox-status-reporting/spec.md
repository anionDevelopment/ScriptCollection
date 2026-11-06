# Spec Delta

## MODIFIED Requirements

### Requirement: The command-line interface of scrais stays unchanged

The status reporting SHALL NOT need an argument of `scrais` or a key of the configuration file: it SHALL NOT add, remove or rename an argument of `scrais` and SHALL NOT add a key to the configuration file.
The reporting is active automatically when the herdr environment variables are present.
Arguments and keys which other capabilities add (for example the build-environment or the network-access) are not part of this requirement.

#### Scenario: Argument list is compared

- **WHEN** the argument definitions of `scrais` are compared with the ones without the status reporting
- **THEN** the status reporting contributes no argument and no key of the configuration file, and names, short names, actions and defaults of the other arguments are identical
