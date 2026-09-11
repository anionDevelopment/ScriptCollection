# Testcases Specification

## Purpose

Records what a testcase of this product may do. The product automates builds and therefore talks to servers in several
places - task-runners, registries, git-remotes, container-registries - which makes it tempting to verify that by really
talking to one. A testcase which does that no longer states something about the code of this product: its result then
also depends on whether something is reachable, on a port being free and on what a third party currently answers.

## Requirements

### Requirement: A testcase does not communicate with a server

A testcase SHALL NOT send a request to a server and SHALL NOT verify that a connection to one can be established. This
holds for every kind of server: one which the testcase starts itself, one which runs somewhere in the network of the
executing machine, and one which is reachable over the internet.

A testcase SHALL therefore be executable on a machine without network-access, and its result SHALL be the same on every
machine which has the source-code of this product.

#### Scenario: The code under test communicates with a server

- **WHEN** a testcase covers code which sends requests to a server
- **THEN** the part which does the communication is separated from the logic and is replaced in the testcase, so that
  the testcase exercises the logic and no request leaves the process

#### Scenario: A behaviour can only be exercised with a real server

- **WHEN** a behaviour can only be exercised by really running a server and really talking to it
- **THEN** that verification is done outside of the testsuite and is not committed, and what is committed is the part
  which can be exercised without a server

#### Scenario: A testcase would start a server of its own

- **WHEN** a testcase would start a server - also one which only listens on the local machine - to talk to it
- **THEN** that is not allowed either: a testcase must not depend on a port being free, on a firewall or on the timing
  of a process which is started next to it

#### Scenario: A testcase would use an address of the internet

- **WHEN** a testcase would use an address which is reachable over the internet, for example to verify a download, a
  registry-query or the availability of a service
- **THEN** that is not allowed: the result of the testrun would state something about that third party and about the
  network, and not about this product
