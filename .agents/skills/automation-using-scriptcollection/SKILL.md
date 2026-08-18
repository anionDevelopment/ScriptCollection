---
name: "automation-using-scriptcollection"
description: "Contains information about the automations provided by ScriptCollection and how to use them, especially in repositories which implement the \"common project structure\"."
purpose: "Information about automation using ScriptCollection."
tags: information, automation, conventions
version: 1.5.42
---

# General

## General information

`ScriptCollection` is a python-package which contains reusable automations for building, testing, linting, releasing and maintaining software-projects.

- Source-code: https://github.com/anionDevelopment/ScriptCollection (mirror: https://github.com/anionDev/ScriptCollection)
- Package: `ScriptCollection` on PyPI (installable via `pip install ScriptCollection`)
- Reference: https://aniondev.github.io/ScriptCollectionReference/index.html

ScriptCollection provides two kinds of entrypoints:

1. **Commandline-commands** (all prefixed with `sc`, for example `scbuildcodeunits`), which are available as global commands after installing the package.
2. **Python-API** (most importantly the `ScriptCollection.TFCPS`-module, "TFCPS" = "Tasks For Common Project Structure"), which is imported by the scripts inside a repository.

### How to recognize that a repository uses ScriptCollection

A repository implements its automation with ScriptCollection if at least one of the following is true:

- `<repository>/.ScriptCollection/` exists (usually containing `ProductInformation.xml`).
- The python-scripts of a codeunit (for example `<codeunit>/Other/Build/Build.py`) import from `ScriptCollection.TFCPS`.
- `<repository>/Taskfile.yml` exists and contains tasks like `BaseBuildAllCodeunits` which call `sc...`-commands.

Implementing the "common project structure" and implementing it *with ScriptCollection* are two different things: the "common project structure" only defines *which* scripts must exist and *what* they must do, not *how* they are implemented. ScriptCollection is one (the usual) implementation of it. If a repository only implements the common project structure without ScriptCollection then only the conventions apply, not the concrete commands described here.

# Work with common-project-structure

This section describes how the automation of a repository which implements the "common project structure" works when it is implemented using ScriptCollection. For the conventions of the common project structure itself see the skill `work-with-common-project-structure`.

## The scripts of a codeunit

The whole build-pipeline is implemented as python-scripts at defined locations inside the codeunit. These scripts are mostly thin wrappers which delegate to ScriptCollection, so the actual logic is usually not duplicated in the repository.

| Script | Purpose |
|---|---|
| `<codeunit>/Other/CommonTasks.py` | Preparation-tasks, for example updating the version and building/copying dependent codeunits. |
| `<codeunit>/Other/UpdateDependencies.py` | Updates the dependencies of the codeunit. |
| `<codeunit>/Other/QualityCheck/Linting.py` | Runs the linting. Exits non-zero on linting-issues. |
| `<codeunit>/Other/QualityCheck/RunTestcases.py` | Runs the testcases, generates the test-coverage and checks the minimal-code-coverage-threshold. |
| `<codeunit>/Other/Reference/GenerateReference.py` | Generates the html-reference from `<codeunit>/Other/Reference/ReferenceContent`. |
| `<codeunit>/Other/Build/Build.py` | Builds the productive build-artifacts (without unit-tests). |
| `<codeunit>/Other/OnBuildingFinished.py` | Optional script for tasks which run after all other scripts. |

All of these scripts are runnable unattended on every developer-machine, they exit with 0 on success and with a non-zero exit-code on failure. Running the whole pipeline is idempotent: it must not change any not-git-ignored file.

Because these scripts only delegate to ScriptCollection, a change of the pipeline-behaviour usually does not belong into the repository but into ScriptCollection itself.

## Build the codeunits

| Command | Purpose |
|---|---|
| `scbuildcodeunits` | Runs all scripts of all enabled codeunits (in the correct order regarding the dependencies between the codeunits) directly on the machine. |
| `scbuildcodeunits -c` | Same, but runs the scripts inside a container which provides a standardized environment (`-c` = `--runincontainer`). |
| `scbuildcodeunitsc` | Shortcut for `scbuildcodeunits -c`. |
| `scupdatedependencies` | Runs the `UpdateDependencies.py` of all codeunits. |

Relevant switches of `scbuildcodeunits`:

- `-r`/`--repositoryfolder`: the repository to build (default: current folder).
- `-e`/`--targetenvironment`: the target-environment (default: `QualityCheck`, productive builds use `Productive`).
- `-v`/`--verbosity`: the loglevel (higher value = more output; useful when analyzing a failing build).
- `-f`/`--fastlane`: skips `RunTestcases.py` (useful for a quick check, but not sufficient to consider a change verified).
- `-n`/`--nocache`: does not use cached tools/resources.
- `-u`/`--assertnonewchanges`: fails if the pipeline changes a not-git-ignored file (verifies the idempotency).

If the command exits with 0 then everything is fine. If it exits with a non-zero exit-code then there is an error and the output of the command has to be checked for details.

`scbuildcodeunits` also does some preparation-steps automatically; see the next section for which files it generates and synchronizes.

## Files which are generated and synchronized automatically

Some files of a repository are not maintained by hand but are derived from another file or from another folder. "Automatically" and "always" mean the same thing everywhere in this document: **it happens every time the codeunits are built with `scbuildcodeunits`** (and therefore also with `task bb` and in the build-pipeline). None of these files has to be generated by hand, and none of them may be edited by hand — a manual change is lost with the next build. Change the source instead.

| File / folder | Derived from | Note |
|---|---|---|
| `<repository>/Taskfile.yml` | `<repository>/<projectname>.code-workspace` | To add or change a task, change the `tasks`-section of the workspace-file. |
| The skill-folders of the other agents | `<repository>/.agents/skills` | See below. |
| The diagrams which are based on plantuml | the corresponding `.puml`-files | The generated diagrams are always regenerated, so a change belongs into the `.puml`-file. |
| The codeunits-overview-diagram | the codeunits and their dependencies | |

Additionally the line-endings of all text- and sourcecode-files are normalized to **LF**. Do not commit files with CRLF-line-endings: they are changed back, which shows up as a difference nobody made.

### Skills

- The folder `<repository>/.agents/skills` is the **single source of truth** for the skills of a repository. Every skill which belongs to the repository is created and changed there.
- The skill-folders of the other agents are **synchronized from it automatically**. Never edit a skill in one of those folders: the change is lost as soon as the codeunits are built again.
- The exception are the **openspec-skills**: they are managed by openspec itself, so they are neither written nor changed by hand.

## Tasks

Repositories usually contain a `Taskfile.yml` in the repository-root which can be executed with [Task](https://taskfile.dev), for example `task UpdateVisualRegressionBaselines`.

Important properties of `Taskfile.yml`:

- It is **generated** from the `.code-workspace`-file of the repository (by `scgeneratetaskfilefromworkspacefile`, which is also executed as part of `scbuildcodeunits`). Therefore `Taskfile.yml` must never be edited manually: to add or change a task, change the `tasks`-section of the `<repository>/<repository>.code-workspace`-file and regenerate the `Taskfile.yml`.
- Every task has a long name (for example `UpdateVisualRegressionBaselines`), a lowercase-alias (`updatevisualregressionbaselines`) and a short alias (`uvrb`). All of them can be used.
- `task --list` shows all tasks which are available in the current repository.

Tasks which commonly exist (which tasks exist really depends on the repository):

| Task (short alias) | Purpose |
|---|---|
| `BaseBuildAllCodeunits` (`bb`) | Runs `scbuildcodeunits`. |
| `BaseBuildAllCodeunitsContainerized` (`bd`) | Runs `scbuildcodeunitsc`. |
| `BaseUpdateDependencies` (`bud`) | Runs `scupdatedependencies`. |
| `UpdateVisualRegressionBaselines` (`uvrb`) | Regenerates the baseline-screenshots of the visual-regression-tests (see below). |
| `Translate` (`t`) | Updates the translation-files. Is also executed automatically by `scbuildcodeunits` if the task exists. |
| `BaseExampleStart` (`beu`) / `BaseExampleStop` (`bed`) | Starts/stops the example-instance of the product (usually a docker-compose-setup). |
| `LocaltestserviceMariadbStart` (`ldmu`) / `LocaltestserviceMariadbStop` (`ldmd`) | Starts/stops the local MariaDB-testservice. |
| `LocaltestservicePostgresqlStart` (`ldpu`) / `LocaltestservicePostgresqlStop` (`ldpd`) | Starts/stops the local PostgreSQL-testservice. |
| `LocaltestserviceReverseProxyStart` / `LocaltestserviceReverseProxyStop` | Starts/stops the local reverse-proxy-testservice. |
| `RunFrontend` (`rf`) | Starts the frontend-codeunit in development-mode. |

Some testcases require that the corresponding local testservices are running. If testcases which need a database or a reverse-proxy fail, first check whether the required `Localtestservice...`-task was started.

## Visual-regression-tests

If a codeunit has visual-regression-tests then:

- The tests themselves are located in `<codeunit>/Other/QualityCheck/VisualRegressionTests` (usually a playwright-project) and are executed as part of `RunTestcases.py`.
- The baseline-screenshots are located in `<codeunit>/Other/Resources/VisualRegressionBaselines` in the structure `<browser>/<platform>/<name>.png`. They are not git-ignored and belong to the repository.
- The screenshots are generated inside a container so that they are reproducible independently of the operating-system of the developer.

If the visual appearance was changed intentionally then the baseline-screenshots are outdated and the visual-regression-tests will fail. In this case the baselines have to be regenerated with:

```
task UpdateVisualRegressionBaselines
```

(Alternatively the underlying script `<codeunit>/Other/QualityCheck/UpdateVisualRegressionBaselines.py` can be executed directly in its folder.)

Rules for this:

- Only regenerate the baselines if the change of the appearance was **intended**. A failing visual-regression-test is a finding first and has to be understood before the baselines are overwritten.
- Review the resulting image-diff before committing: the regenerated baselines are the new expectation.
- The regenerated baseline-screenshots have to be committed together with the change which caused them.

## Changelog and version

| Command | Purpose |
|---|---|
| `scshowprojectversion` | Prints the current version of the product/repository (calculated by gitversion). |
| `sccreatechangelogentry` | Creates the changelog-entry-file for the current version (`-m` for the message, `-c` to commit it directly). |
| `scshowversion` | Prints the version of the installed ScriptCollection itself (**not** the version of the project). |

The changelog is located in `<repository>/Other/Resources/Changelog` and the file for the current version is `v<version>.md`. Determine `<version>` with `scshowprojectversion` **after** the changes were implemented, because the version can change with the changes.

## Release

| Command | Purpose |
|---|---|
| `sccreaterelease` | Creates a release of a repository which uses the anion-build-platform (`-s` for the source-branch, `-u` to update the dependencies as part of the release). |
| `sccreatesimplemergewithoutrelease` | Merges a branch into another one without creating a release. |
| `scpreparebuildpipelineforgithub` / `scpreparebuildpipelineforgitlab` | Generates/updates the CI-pipeline-definition for GitHub respectively GitLab. |

# Further automations of ScriptCollection

Besides the pipeline, ScriptCollection contains a lot of general-purpose-commands. The most relevant ones:

## Quality and security

| Command | Purpose |
|---|---|
| `scsearchforsecrets` | Scans a repository for secrets. Known false-positives are allowlisted in `.betterleaks.toml`. |
| `scsearchforsecretsinimage` | Scans an OCI-image which is available in the local docker-instance for secrets. |
| `scloc` | Counts the lines-of-code of the repository. |
| `sccheckpythonast` | Checks python-files by analyzing their AST. |
| `scsearchinfiles` | Searches a regex in the files of a folder. |
| `scshowmissingfiles` | Shows files which are expected but missing. |

## Dependencies and tools

| Command | Purpose |
|---|---|
| `scupdatenugetpackagesincsharpproject` | Updates the nuget-packages of a C#-project. |
| `scupdateimagesindockercomposefile` | Updates the image-versions in a docker-compose-file. |
| `scdownloadcachabletools` | Downloads the external tools which the pipeline needs into the local cache. |
| `sccleantoolscache` | Clears this cache. |
| `scnpmi` | Runs an `npm install` in a defined way. |

## Docker

| Command | Purpose |
|---|---|
| `scensuredockernetworkisavailable` / `scensuredockernetworkisnotavailable` | Ensures that a docker-network exists respectively does not exist. |
| `scensureexternaldockernetworksexist` | Ensures that all external docker-networks exist. |
| `scshowexternaldockernetworks` | Shows the external docker-networks. |
| `screclaimspacefromdocker` | Frees disk-space used by docker. |
| `scaddimagetocustomregistry` | Adds an image to a custom registry. |

## Certificates

| Command | Purpose |
|---|---|
| `scgeneratecertificateauthority` | Generates a certificate-authority (for development-purposes). |
| `scgeneratecertificate` | Generates a certificate. |
| `scgeneratecertificatesignrequest` | Generates a certificate-sign-request. |
| `scsigncertificate` | Signs a certificate. |

## Documentation and generation

| Command | Purpose |
|---|---|
| `scgeneratetaskfilefromworkspacefile` | Generates `Taskfile.yml` from the `.code-workspace`-file. |
| `scgeneratearc42referencetemplate` | Generates an arc42-reference-template. |
| `scsyncxlffiles` | Synchronizes xlf-translation-files. |
| `sccreateskill` | Creates the skeleton of a new skill. |

## Miscellaneous

There are further commands for file- and folder-operations (`sccopy`, `screname`, `scremovefile`, `scnormalizelineendings`, ...), for media (`scmergepdfs`, `scextractpdfpages`, `scgeneratethumbnail`, `scocranalysisof...`) and for other purposes. Every command supports `--help`, so if a command looks relevant, check its help-output instead of guessing its arguments. The complete list of commands is defined in the `[project.scripts]`-section of the `pyproject.toml` of the ScriptCollection-codeunit.
Running `scbuildcodeunits` in parallel on multiple repositories might result in errors depending on the used automations.

# Find out what a function really does

This document describes what the automations are for, not how they are implemented. Whenever the exact behaviour of a command or of a function matters — which arguments it really accepts, in which order it does its steps, which files it touches, under which condition it fails — do not guess it and do not derive it from its name: **read its source-code** at https://github.com/anionDevelopment/ScriptCollection (mirror: https://github.com/anionDev/ScriptCollection).

Where to look:

- `ScriptCollection/Executables.py` contains one function per `sc...`-commandline-command, including the definition of its arguments. The mapping from the command-name to that function is in the `[project.scripts]`-section of the `pyproject.toml` of the ScriptCollection-codeunit.
- `ScriptCollection/TFCPS/` contains the pipeline-logic which the scripts of a codeunit delegate to (per codeunit-type in the subfolders, for example `TFCPS/DotNet` and `TFCPS/NodeJS`).
- `ScriptCollection/ScriptCollectionCore.py` and `ScriptCollection/GeneralUtilities.py` contain the general-purpose-functions which the rest uses.

The installed package contains the same python-files, so reading them locally (in the `site-packages`-folder of the used python-installation) is usually faster than looking them up in the repository — but be aware that the installed version can be older than the repository, which matters exactly when a behaviour was changed recently.

If the behaviour turns out to be wrong or missing, the fix belongs into the ScriptCollection-repository (see the hints below).

# Hints

- Do not implement automation-logic redundantly in a repository if ScriptCollection already provides it. If something is missing or wrong in the automation, the fix usually belongs into the ScriptCollection-repository, not into the repository in which the problem was noticed.
- Do not edit generated files (`Taskfile.yml`, generated diagrams, generated references, the synchronized skill-folders) manually. Change their source and regenerate them. See "Files which are generated and synchronized automatically".
- Never bypass a failing script (for example by lowering the code-coverage-threshold or by regenerating baselines) without having understood the failure first.