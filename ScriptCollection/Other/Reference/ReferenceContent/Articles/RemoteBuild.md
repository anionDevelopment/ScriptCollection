# Remote-build (operating-system-bound build-steps)

## Overview

Some build-steps can only be produced on a specific operating-system, or require a toolchain (e.g. the Android-SDK/NDK) that
is deliberately not part of the general-purpose Debian-build-pipeline-image anymore:

- Flutter `windows`-builds must be built on Windows.
- Flutter `macos`-desktop-builds and `ios`-builds must be built on macOS.
- Flutter `appbundle`-builds (Android) require the Android-SDK/NDK, which lives only in the dedicated
  `SCTaskRunnerAndroid`-image, not in SCBuilder itself.

Neither the (Linux) Debian-build-pipeline nor (for macOS/iOS) a Windows-developer-client can produce these. ScriptCollection
therefore delegates such operating-system-/toolchain-bound steps to a **remote task-runner** that provides the required
operating-system (or, for Android, the required toolchain inside a Linux-container).

The mechanism is generic and available to every codeunit-type (it lives in `TFCPS_CodeUnitSpecific_Base`, not only in the
flutter-codeunit): `self.run_program_on_remote_runner(required_os, program, arguments, working_directory)`. The actual
transport/synchronization is implemented in `TFCPS_RemoteBuild`; the runners are the codeunits `SCTaskRunnerWindows`,
`SCTaskRunnerMacOS`, `SCTaskRunnerIOS` and `SCTaskRunnerAndroid` (in the SCBuilder-repository), which each expose an
HTTP-server. `RunnerOperatingSystem.MacOS` and `RunnerOperatingSystem.IOS` are deliberately two separate values (not one
shared "macOS" value) so that a macOS-desktop-build and an iOS-build of the same repository can be delegated to two
different runners.

Flutter's `linux`-target is *not* part of this mechanism, even though it is also operating-system-bound in the sense that
it needs the Linux-desktop-toolchain (clang/cmake/ninja/libgtk-3-dev): the (Linux-based) build-pipeline itself already runs
on Linux, it just does not have that toolchain installed directly, so `TFCPS_CodeUnitSpecific_Flutter` instead runs
`flutter build linux` in a plain, ad-hoc sibling-container of the `SCBuilder`-image (started and removed just for that one
build-step) rather than delegating to a permanently-running task-runner.

## Flow

1. The client packs the **whole repository** (including the `.git`-folder, uncommitted changes and git-ignored files) into
   a tar-archive and sends it over HTTPS to the runner that provides the required operating-system.
   - git-ignored files and uncommitted changes are included on purpose: they are sometimes required for the build (for
     example signing-certificates for windows-builds). The runner is part of the build-infrastructure and is trusted exactly
     like the machine/container on which `scbuildcodeunits` runs and from which such secrets originate; therefore there is
     **no** secret-exclude-filter.
2. The runner answers the submit **as soon as the archive has arrived** and does everything else in the job: it extracts
   the archive into a **fresh, empty workspace** (isolation), runs the requested program on its operating-system, and
   returns **only the folder the client stated its result is in** (the client sends it as `X-Result-Folder`).
   - The extraction belongs to the job and not to the submit-request, because extracting the repository of a large
     codeunit takes minutes during which no data flows - the client and a reverse-proxy between them would run into
     their timeouts although the job is being prepared correctly. A client therefore sees a job which is already running
     while its repository is still being extracted, and a failing extraction is a failed job, not a failed request.
3. The client **writes the returned content into that same folder** of the local repository, so the build-step can
   continue with the result as if it had been produced locally. **Nothing is deleted for this** and nothing else of the
   local repository is touched.
4. The client deletes the job on the runner, which **deletes the runner-workspace immediately**, so no repository-content
   remains on the runner.

## Which error reaches the client

A runner separates a build which does not work from a runner which does not work:

- **The build fails** (the app does not compile, a test fails, whatever the delegated program reports): that is what the
  client asked for, so its **complete output** is transferred and printed, and the job ends with the exitcode of that
  program.
- **The runner itself fails** (it can not extract the transferred repository, can not start the program, or any other
  unexpected error): the client gets the statement that the runner failed plus an **error-id**, and a request which fails
  this way is answered with **500** without details. The details - stacktraces and paths inside the runner - are written
  to the log of the runner only, under that same error-id, because they state something about the internals of that
  runner which the one who waits for the build can not act on.

## What an interrupted connection to a runner means

A job runs on the runner independently of the connection to the client: an interrupted connection does not stop the build,
and a runner states the result of every job it ran in its own log, also when no client is waiting for it any more.

The client therefore distinguishes two things while it waits for a job:

- The runner **answered** - including with an error-status. That is a defined answer and is reported immediately.
- The runner **could not be reached** (the connection was refused, reset or its answer was cut off). Requests which
  concern a job that already exists are then repeated for at most **five minutes**, because the build they belong to is
  still producing a result in the meantime. Submitting a job is never repeated: that would start a second build.

An interruption which lasts longer ends the build with the statement that its result is unknown here and that it may still
be running on the runner. A runner which is restarted meanwhile does not know the job any more (a runner holds its jobs in
memory only), which the client reports as exactly that instead of as an unspecific `404`.

A connection counts as interrupted when it transports nothing for **five minutes**. The exception is fetching the result:
the runner packs the complete build-output of the codeunit before it sends the first byte of it, so nothing is
transported while that runs, and the client waits **an hour** for that one request. This has to stay above the
read-timeout of a reverse-proxy in front of a runner, so that its gateway-timeout - a defined answer - arrives instead of
the client giving up on the connection first.

## Why only the result-folder comes back

A build-step produces its result in a folder which the code that delegates it already knows - a flutter-windows-build in
`build/windows/x64/runner/Release`, an android-appbundle-build in `build/app/outputs/bundle/release`, and so on; that is
the folder the artifacts are copied from afterwards. Everything else which changed in the workspace of the runner is not
a result:

- **State of that machine**: `local.properties` pointing at the SDK-path of the runner, `.dart_tool`-files containing its
  absolute paths, caches. Written into the repository of a developer, these are wrong there.
- **Content the client sent itself**, unchanged - there is no point in sending it back.

The earlier behaviour (replacing the whole codeunit-folder with the one of the runner) additionally **deleted** the local
codeunit-folder first. That destroys everything of that codeunit which is not part of the answer of the runner, including
files which are not in git and can therefore not be restored, and on Windows it can not even complete: the build-script
of the codeunit runs in a folder below the codeunit, a folder a process runs in can not be removed there, so the deletion
fails in the middle and leaves the codeunit incomplete.

## Why windows-, macos-, ios- and appbundle-builds always use a runner

The flutter-codeunit delegates `windows`-, `macos`-, `ios`- and `appbundle`-builds to a runner **unconditionally** - even a
windows-build started on a Windows-developer-client is delegated to the Windows-runner. The reason is **uniform builds**:
every build of a given target is produced in the same, defined environment, independent of which developer-machine or
pipeline triggered it. This avoids subtle differences between locally-built and pipeline-built artifacts. For `appbundle`
there is the additional reason that the Android-SDK/NDK is not installed anywhere except on the Android-runner.

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

The runners are the codeunits `SCTaskRunnerWindows`, `SCTaskRunnerMacOS`, `SCTaskRunnerIOS` and `SCTaskRunnerAndroid` in the
SCBuilder-repository. `SCTaskRunnerWindows`, `SCTaskRunnerMacOS` and `SCTaskRunnerIOS` run natively on a Windows-
respectively macOS-host (there are no macOS-containers, and the native toolchains - Visual Studio, Xcode - are required).
`SCTaskRunnerAndroid` runs as a **container** instead - unlike a Windows- or macOS-toolchain, the Android-SDK/NDK works
inside a Linux-container, so it is delivered as a permanently-running container-image (analogous in spirit to how
SCGitHubRunner is a permanently-running container) instead of a native installation. All of them share the same
server-logic, which lives in `ScriptCollection.TFCPS.SCTaskRunnerServer`.
