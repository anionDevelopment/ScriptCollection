---
name: "work-with-common-project-structure"
description: "Contains information about the \"common project structure\" and how to work with it."
purpose: "Information about repository-conventions."
tags: information, conventions
version: 1.5.42
---

# General

## General information

The "common project structure" is a set of conventions and best practices for organizing and structuring a software project defined by: https://projects.aniondev.de/PublicProjects/Common/ProjectTemplates/-/raw/main/Conventions/RepositoryStructure/CommonProjectStructure/CommonProjectStructure.md
It follows convention-over-configuration, so most things are located at a well-defined place and do not have to be searched for.

### Codeunits

A repository contains one or more `codeunit`s. A codeunit is an independently compilable part of the product (for example a library, a backend, a frontend or an image-definition). Small products have exactly one codeunit, larger ones (monorepos) have several.

- A codeunit is located in `<repository>/<codeunit>`, its source-code usually in `<repository>/<codeunit>/<codeunit>` and its testcases in `<repository>/<codeunit>/<codeunit>Tests`.
- Testcases belong to the codeunit and are a mandatory part of it (as long as the codeunit has testable source-code).
- Each codeunit has its own version, which is independent of the product-version.
- Build-results are placed in `<codeunit>/Other/Artifacts/<artifactname>` (git-ignored). Common artifacts: `BuildResult_<TargetEnvironment>`, `TestCoverage`, `TestCoverageReport`, `Reference`, `BOM`, `APISpecification`.

### How a codeunit may use another codeunit

A codeunit is only allowed to use another codeunit of the same repository under two conditions, and both of them apply to the source-code as well as to the scripts of the codeunit:

1. **The other codeunit is declared as a dependency.** Its name has to be listed in the `dependentcodeunits`-element of `<repository>/<codeunit>/<codeunit>.codeunit.xml`. What is not declared there must not be used, even if it exists in the same repository.
2. **It is used through `<codeunit>/Other/Resources/DependentCodeUnits`.** That folder contains the build-artifacts of the declared dependencies, and it is the only permitted way to reach anything of another codeunit: constants, artifacts, generated files, specifications, everything. A codeunit must never reach into the folder of another codeunit directly (no relative path into `../<other codeunit>`, no reference to its source-code or to its `Other/Artifacts`-folder, no copy of one of its files).

The reason for both rules is that a codeunit has to stay independently buildable: the declaration is what tells the pipeline in which order the codeunits have to be built, and the folder is what makes the dependency a real artifact-dependency instead of a hidden coupling to the working-copy of somebody else. A dependency which is used but not declared builds by accident on the machine of the developer and fails in the pipeline (or, worse, silently uses an outdated state).

Consequently, when a codeunit needs something new from another one: declare the dependency in the `codeunit.xml` first, and take the value out of the artifact — do not copy it and do not duplicate it.

### Automation

The common project structure defines that the whole build-pipeline is implemented as python-scripts at defined locations inside the codeunit (`<codeunit>/Other/CommonTasks.py`, `<codeunit>/Other/UpdateDependencies.py`, `<codeunit>/Other/QualityCheck/Linting.py`, `<codeunit>/Other/QualityCheck/RunTestcases.py`, `<codeunit>/Other/Reference/GenerateReference.py`, `<codeunit>/Other/Build/Build.py` and optionally `<codeunit>/Other/OnBuildingFinished.py`).

**These scripts have to be python-scripts**, at exactly these paths and with exactly these names. That is what makes it possible to run the pipeline of any such repository without knowing anything about the technology of the codeunit: a dotnet-codeunit, a node-codeunit and an image-definition are all built by calling the same file-names. Do not replace one of them by a shell-script, a batch-file or a task of another tool, and do not move the logic into such a file which the python-script only calls: whatever the script needs to do belongs into the script (or into the automation-package behind it).

All of these scripts are runnable unattended on every developer-machine, they exit with 0 on success and with a non-zero exit-code on failure. Running the whole pipeline is idempotent: it must not change any not-git-ignored file.

### Updating dependencies

The update of the dependencies exists on two levels, and both of them are optional:

- `<repository>/Other/UpdateDependencies.py` updates the things which belong to the repository as a whole, so everything which lives in `<repository>/Other` and not in a codeunit.
- `<codeunit>/Other/UpdateDependencies.py` updates the dependencies of one codeunit. Everything which is specific to a codeunit belongs here and not into the script of the repository. Whether a codeunit has one at all is stated in its `codeunit.xml` (`properties/@codeunithasupdatabledependencies`); dependencies which are deliberately not updated are listed in `properties/updatesettings/ignoreddependencies`.

The common project structure only defines **which** scripts must exist and **what** they must do, not **how** they are implemented. The usual implementation is the `ScriptCollection`-package (see https://github.com/anionDevelopment/ScriptCollection): in that case the scripts in the repository are only thin wrappers which delegate to ScriptCollection, so the actual logic is not duplicated in the repository.

**If a repository does not only implement the common project structure but also implements it using ScriptCollection then all knowledge about the concrete automations is contained in the skill `automation-using-scriptcollection`** (see its section "Work with common-project-structure"). That skill describes how the codeunits are built (`scbuildcodeunits`), which tasks exist (`Taskfile.yml`, for example `task UpdateVisualRegressionBaselines` to regenerate the baseline-images of visual-regression-tests) and which further commandline-commands ScriptCollection provides. Consult that skill before running or changing anything automation-related in such a repository.

A repository uses ScriptCollection if `<repository>/.ScriptCollection/` exists, if the scripts listed above import from `ScriptCollection.TFCPS` or if `<repository>/Taskfile.yml` contains tasks which call `sc...`-commands.

## Examples of codeunits

There is a repository which contains one example-codeunit per programming-language and project-type: https://github.com/anionDev/CommonProjectStructureExamples (note that it is located under the user `anionDev` and not under the organization `anionDevelopment`).

It contains for example `DotNetLibraryCodeUnit`, `DotNetConsoleCodeUnit`, `DotNetWebAPICodeUnit`, `DotNetWebAPIClientCodeUnit`, `AngularCodeUnit`, `PythonCodeUnit`, `MavenCodeUnit`, `RustCodeUnit`, `CombinedBackendFrontendCodeUnit` as well as codeunits which only define a container-image (`WebAPIContainerCodeUnit`, `WebAppContainerCodeUnit`).

Use it in these situations:

- **A new codeunit has to be created.** Take the example whose type matches, copy its structure and adapt the names and the content. That is faster and safer than assembling the required files by hand, because the example already contains everything the pipeline expects (the `codeunit.xml`, all scripts, the folder-structure and the reference-content).
- **It is unclear how something has to look for a certain project-type.** The example shows what the concrete implementation of a script or of a configuration looks like for that type - for example how `Build.py` of a dotnet-library differs from the one of an angular-application.
- **A codeunit behaves differently than expected.** Compare it with the example of its type: a difference is usually the reason.

Keep in mind that the examples are minimal on purpose. They show the structure and not a realistic product, so do not copy their content, only their shape.

## Defined source of information

Because of the conventions, information about the product and its codeunits does not have to be guessed. It can be read from defined files:

`<repository>/<codeunit>/<codeunit>.codeunit.xml` (must be valid against `codeunit.xsd`) defines per codeunit:

- `enabled`-attribute: whether the codeunit is built and processed at all. Disabled codeunits are skipped by the pipeline.
- `codeunitspecificationversion`-attribute: the version of the common-project-structure-specification the codeunit implements.
- `name` and `version` of the codeunit.
- `codeunitownername` and `codeunitowneremailaddress` as well as the `developerteam` (name and email-address of each developer).
- `properties/@description`: short description of the codeunit.
- `properties/@developmentstate`: for example "Active development", "Maintenance updates only" or "Inactive".
- `properties/@codeunithastestablesourcecode`: whether the codeunit has testable source-code at all (if `false`, there are no testcases and no `RunTestcases.py`).
- `properties/@codeunithasupdatabledependencies`: whether the codeunit has dependencies which can be updated (if `false`, there is no `UpdateDependencies.py`).
- `properties/testsettings/@minimalcodecoverageinpercent`: the minimum test-coverage-threshold which the testcases must reach.
- `properties/pipelinedemands`: tools (optionally with version) which must be available to build the codeunit.
- `properties/updatesettings/ignoreddependencies`: dependencies which are deliberately not updated.
- `dependentcodeunits`: the names of all codeunits of the same repository this codeunit depends on.

`<repository>/.ScriptCollection/ProductInformation.xml` (must be valid against `productinformation.xsd`) defines per product/repository:

- `producttitle`: the name of the product.
- `remoteaddress`: the address of the remote-repository.
- `requiredenvironmentvariables`: the names (not the values) of the environment-variables which must be set to build the product.

Further defined sources are the `ReadMe.md`-files (product- and codeunit-level, including the development-state), `<codeunit>/Other/Reference/ReferenceContent/Hints.md` (requirements to run the scripts) and `HowToBuild.md`, and `GitVersion.yml` for the versioning.

## Build codeunits

Building means running all scripts of all enabled codeunits (for building, linting, running the testcases, etc.) in the correct order regarding the dependencies between the codeunits.
In repositories which implement the common project structure using ScriptCollection the pipeline-command for this is `scbuildcodeunits` (with the `-c`-switch it runs the scripts in a container which provides a standardized environment). The details and all further switches are described in the skill `automation-using-scriptcollection`.
If the pipeline-command exits with 0 then everything is fine. If it exits with a non-zero exit-code then there is an error and the output of the command should be checked for details.

## Changelog

The changelog is always located in `<repository>\Other\Resources\Changelog`.
When you change something then then always update the changelog accordingly.
To find the correct changelog-file: Query the current project version. In repositories which use ScriptCollection this is done with `scshowprojectversion` (note that `scshowversion` shows the version of ScriptCollection itself, not the version of the project).
It is important to determine the version after implementing the changes, not before it.
The changelog-filename in the changelog-folder is then `v<version>.md`, where `<version>` is the determined version.