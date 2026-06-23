# Remote-build (operating-system-bound build-steps)

## Overview

Some build-steps can only be produced on a specific operating-system:

- Flutter `windows`-builds must be built on Windows.
- Flutter `ios`-builds must be built on macOS.

Neither the (Linux) Debian-build-pipeline nor (for iOS) a Windows-developer-client can produce these. ScriptCollection
therefore delegates such operating-system-bound steps to a **remote task-runner** that runs on the correct operating-system.

The mechanism is generic and available to every codeunit-type (it lives in `TFCPS_CodeUnitSpecific_Base`, not only in the
flutter-codeunit): `self.run_program_on_remote_runner(required_os, program, arguments, working_directory)`. The actual
transport/synchronization is implemented in `TFCPS_RemoteBuild`; the runners are the codeunits `SCTaskRunnerWindows` and
`SCTaskRunnerMacOS` (in the SCBuilder-repository), which each expose an HTTP-server.

## Flow

1. The client packs the **whole repository** (including the `.git`-folder, uncommitted changes and git-ignored files) into
   a tar-archive and sends it over HTTPS to the runner that provides the required operating-system.
   - git-ignored files and uncommitted changes are included on purpose: they are sometimes required for the build (for
     example signing-certificates for windows-builds). The runner is part of the build-infrastructure and is trusted exactly
     like the machine/container on which `scbuildcodeunits` runs and from which such secrets originate; therefore there is
     **no** secret-exclude-filter.
2. The runner extracts the archive into a **fresh, empty workspace** (isolation), runs the requested program on its
   operating-system, and returns **only the codeunit-folder**.
3. The client **mirrors the returned codeunit-folder** back into the local repository (a full replacement, so additions,
   modifications and deletions of the runner are reflected - regardless of whether files are git-ignored). Afterwards it
   looks exactly as if the runner had built locally.
4. The client deletes the job on the runner, which **deletes the runner-workspace immediately**, so no repository-content
   remains on the runner.

## Why only the codeunit-folder is mirrored back

A build-script must, by definition, never change anything outside of its own codeunit-folder. Therefore mirroring back just
the codeunit-folder is sufficient to reproduce the complete result of the remote build, and it keeps the round-trip small.

## Why windows- and ios-builds always use a runner

The flutter-codeunit delegates `windows`- and `ios`-builds to a runner **unconditionally** - even a windows-build started on
a Windows-developer-client is delegated to the Windows-runner. The reason is **uniform builds**: every build of a given
target is produced in the same, defined environment, independent of which developer-machine or pipeline triggered it. This
avoids subtle differences between locally-built and pipeline-built artifacts.

## Runner-configuration (client-side)

The client needs the URL and basic-auth-credentials of the runners. Two sources are supported (analogous to how custom
NuGet-sources for C#-dependencies are configured):

1. **`~/.ScriptCollection/TFCPS/Runner.csv`** (primarily for developer-clients): one line per runner in the format
   `url;user;password`.
2. **Environment-variables** (primarily for the build-pipeline): `Runner_<name>_URL`, `Runner_<name>_Username` and
   `Runner_<name>_Password`.

If neither source defines a runner, the remote-build fails with an error. The configuration does not state which runner
provides which operating-system; instead each configured runner is queried (via its `GET /os`-endpoint) and the one matching
the required operating-system is used.

## Runners

The runners are the codeunits `SCTaskRunnerWindows` and `SCTaskRunnerMacOS` in the SCBuilder-repository. They run natively on
a Windows- respectively macOS-host (there are no macOS-containers, and the native toolchains - Visual Studio, Xcode - are
required). Their server-logic is shared and lives in `ScriptCollection.TFCPS.SCTaskRunnerServer`.
