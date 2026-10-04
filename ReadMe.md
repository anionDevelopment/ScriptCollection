# ScriptCollection

![Development-state](https://img.shields.io/badge/development--state-active%20development-brightgreen)
![License](https://img.shields.io/badge/license-GPLv3-blue)
![GitHub last commit](https://img.shields.io/github/last-commit/anionDevelopment/ScriptCollection)
![GitHub issues](https://img.shields.io/github/issues-raw/anionDevelopment/ScriptCollection)

## General

ScriptCollection is the place for reusable scripts.
The details can be found [here](https://github.com/anionDevelopment/ScriptCollection/tree/main/ScriptCollection).

## Build

This product requires to use `scbuildcodeunits` implemented/provided by [ScriptCollection](https://github.com/anionDevelopment/ScriptCollection) to build the project.

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

- **`GeneralUtilities.get_version_parts` accepts versions with arbitrary separators.** The dots in its regex
  `^(\d+).(\d+).(\d+)$` are not escaped, so a string like `1x2x3` is accepted as version `1.2.3` instead of being
  rejected. The fix is to escape the dots (`\.`).

- **`GeneralUtilities.is_ignored_by_glob_pattern` does not reliably reject paths outside the source-directory.** The
  check whether the path is located inside the source-directory is a plain `startswith`, so a sibling-folder with a
  shared prefix (for example `/folder/src2/a.txt` for the source-directory `/folder/src`) passes the check; the
  relative path then starts with `..` and can still be matched by patterns like `*`. The fix is to compare against the
  source-directory plus a trailing path-separator, as `ScriptCollectionCore.path_is_allowed_within_base_folder`
  already does.

- **`GeneralUtilities.replace_underscores_in_text` never terminates for self-referencing replacements.** If a value
  contains its own placeholder (for example `{"a": "__a__"}`) or two values reference each other, the replacement-loop
  runs forever.

- **`GeneralUtilities.timedelta_to_simple_string` is wrong for durations of 24 hours or more.** It formats a datetime
  with `%H`, so the days are dropped and for example 25 hours are shown as `01:00:00`.

- **The error-messages of `translate_safe` name a wrong path.** In the NodeJS- and Flutter-codeunit-specific classes
  the message says that the translation-service has to be configured in
  `~/.ScriptCollection/TranslationServiceProperties.txt`, while the file is actually read from
  `~/.ScriptCollection/GlobalCache/TranslationServiceProperties.txt`.

- **`scprintfilecontent` checks a different file than it reads when `-b` is not the current working-directory.** A
  relative `-p` is resolved against `-b` for the check whether reading is allowed, but the file is then read relative
  to the current working-directory. With `-b .` (the default) both are the same; with any other base-folder a file
  outside the base-folder or inside an excluded folder can be read. The fix is to read the same resolved path which
  was checked.

- **The testcase `get_latest_version` in `test_GeneralUtilities.py` never runs.** Its name has no `test_`-prefix, and
  its expectation is wrong as well: it expects `3.1.0` as latest version of `["2.3.4","3.1.0","16.5"]`, although `16.5`
  is not even a valid version for `get_latest_version`. The intended behavior is covered by the
  `test_get_latest_version_*`-testcases, so the testcase can be removed.

## Changelog

See the [Changelog-folder](./Other/Resources/Changelog).

## Contribute

Contributions are always welcome.

This product has the contribution-requirements defined by [DefaultOpenSourceContributionProcess](https://projects.aniondev.de/PublicProjects/Common/ProjectTemplates/-/blob/main/Conventions/Contributing/DefaultOpenSourceContributionProcess/DefaultOpenSourceContributionProcess.md).

## Repository-structure

This product uses the [CommonProjectStructure](https://projects.aniondev.de/PublicProjects/Common/ProjectTemplates/-/blob/main/Conventions/RepositoryStructure/CommonProjectStructure/CommonProjectStructure.md) as repository-structure.

## Branching-system

This product follows the [GitFlowSimplified](https://projects.aniondev.de/PublicProjects/Common/ProjectTemplates/-/blob/main/Conventions/BranchingSystem/GitFlowSimplified/GitFlowSimplified.md)-branching-system.

## Versioning

This product follows the [SemVerPractise](https://projects.aniondev.de/PublicProjects/Common/ProjectTemplates/-/blob/main/Conventions/Versioning/SemVerPractise/SemVerPractise.md)-versioning-system.

## License

See [License.txt](./License.txt) for license-information.
