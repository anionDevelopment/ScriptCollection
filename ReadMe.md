# ScriptCollection

![Development-state](https://img.shields.io/badge/development--state-active%20development-brightgreen)
![License](https://img.shields.io/badge/license-GPLv3-blue)
![GitHub last commit](https://img.shields.io/github/last-commit/anionDevevlopment/ScriptCollection)
![GitHub issues](https://img.shields.io/github/issues-raw/anionDevevlopment/ScriptCollection)

## General

ScriptCollection is the place for reusable scripts.
The details can be found [here](https://github.com/anionDev/ScriptCollection/tree/main/ScriptCollection).

## Build

This product requires to use `scbuildcodeunits` implemented/provided by [ScriptCollection](https://github.com/anionDev/ScriptCollection) to build the project.

## Known issues

- **A containerized build (`scbuildcodeunits -c`/`scbuildcodeunitsc`) can not build a codeunit whose own scripts
  start a container themselves.** The scripts of a codeunit are executed inside the build-container then, and a
  script which starts a container of its own from there has no way to do so: it would have to start a sibling of
  the build-container instead of a container inside it. Found in the repository AthenaTournamentManager (ATM),
  whose visual-regression-tests (`Other/QualityCheck/VisualRegressionContainer.py`) start an SCBuilder-container to
  render their screenshots reproducibly, and whose linux-build does the same; that repository therefore has to be
  built with the non-containerized `scbuildcodeunits`. Not analyzed yet whether the fix belongs into
  ScriptCollection (making the container-execution able to start siblings, for example by passing the
  docker-socket into the build-container) or into the affected codeunit (detecting that it already runs inside the
  build-container and doing its work directly instead of starting a container of its own).

- **The bill-of-materials of a node-codeunit is not written when one of its packages has an unsatisfied optional
  peer-dependency.** `cyclonedx-npm` runs `npm ls --json --long --all`, and npm reports an optional
  peer-dependency which is present in another version as `invalid` and exits non-zero - although an optional peer
  which does not fit is a legitimate state, not a broken installation. `cyclonedx-npm` aborts on that exit-code, so
  the codeunit gets no BOM-artifact at all, while the build itself still reports success. Found in the repository
  AthenaTournamentManager (ATM): its codeunit `AthenaWebsite` has `jsdom` (through the vitest-testsetup), whose
  `@exodus/bytes` declares `@noble/hashes` as an optional peer in `^1.8.0 || ^2.0.0`, while `pkijs` (through
  `@angular-devkit/build-angular`) pins the same package to exactly `1.4.0`; `AthenaWebsite` is therefore the only
  codeunit of that repository without a BOM. The fix belongs where the tool is called (`cyclonedx-npm` has
  `--ignore-npm-errors` for exactly this case) and not into the affected repository, where the only way out would
  be to override a version which another package pins on purpose. Note that the `npm install --force` which the
  node-codeunit-automation does hides such a conflict instead of reporting it, which is why it only shows up here.

## Changelog

See the [Changelog-folder](./Other/Resources/Changelog).

## Contribute

Contributions are always welcome.

This product has the contribution-requirements defines by [DefaultOpenSourceContributionProcess](https://projects.aniondev.de/PublicProjects/Common/ProjectTemplates/-/blob/main/Conventions/Contributing/DefaultOpenSourceContributionProcess/DefaultOpenSourceContributionProcess.md).

## Repository-structure

This product uses the [CommonProjectStructure](https://projects.aniondev.de/PublicProjects/Common/ProjectTemplates/-/blob/main/Conventions/RepositoryStructure/CommonProjectStructure/CommonProjectStructure.md) as repository-structure.

## Branching-system

This product follows the [GitFlowSimplified](https://projects.aniondev.de/PublicProjects/Common/ProjectTemplates/-/blob/main/Conventions/BranchingSystem/GitFlowSimplified/GitFlowSimplified.md)-branching-system.

## Versioning

This product follows the [SemVerPractise](https://projects.aniondev.de/PublicProjects/Common/ProjectTemplates/-/blob/main/Conventions/Versioning/SemVerPractise/SemVerPractise.md)-versioning-system.

## License

See [License.txt](./License.txt) for license-information.
