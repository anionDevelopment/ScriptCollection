## 1. `RepositoryHistoryAnalyzer`

- [x] 1.1 Create `ScriptCollection/ScriptCollection/RepositoryHistoryAnalyzer.py` with the `GitHistoryScale`-enum
      (`Day`, `Week`, `Year`) and the `CommitterActivityDataPoint`/`CommitterActivityData`-dataclasses, and verify
      the module imports without error.
- [x] 1.2 Implement `RepositoryHistoryAnalyzer.get_committers(repository_path)` (parses `git shortlog -n -s HEAD`)
      and `get_committer_emails(repository_path)` (parses `git shortlog -n -s -e HEAD`), and verify both against a
      scripted temporary git-repository with at least two committers.
- [x] 1.3 Implement the shared, private commit-log parsing helper (`git log --pretty=format:%cI<TAB>%cn`) used by
      the three data-aggregation methods below, and verify it returns one `(committer, datetime)`-tuple per commit
      of the scripted temporary repository, in the recorded UTC-offset.
- [x] 1.4 Implement `get_git_history_data(repository_path, scale)` (bucketing by day/ISO-week/year depending on
      `scale`) and verify with unit tests for all three `GitHistoryScale`-values against the scripted repository,
      including the committer-ordering/identities matching `get_committers`.
- [x] 1.5 Implement `get_commits_per_weekday_data(repository_path)` (bucketing by weekday-name) and
      `get_commits_per_hour_data(repository_path)` (bucketing by zero-padded hour), and verify both with unit tests
      against the scripted repository (commits at known, different weekdays/hours).
- [x] 1.6 Add `ScriptCollectionTests/test_RepositoryHistoryAnalyzer.py` covering 1.2-1.5, run with `pytest` and
      verify all tests pass.

## 2. `RepositoryDiagramGenerator`

- [x] 2.1 Create `ScriptCollection/ScriptCollection/RepositoryDiagramGenerator.py` with the private
      `CommitterActivityData` -> `datasets.committerEmails`-array helper and the private legend-`encode`-block
      helper (the `pluck`/`indexof`-based email-tooltip from design.md), and verify with a unit test that the
      helper's output is valid JSON-serializable data for a sample `CommitterActivityData`.
- [x] 2.2 Implement the shared private line/point-diagram spec-builder (bucket-field on `x`, `Commits` on `y`,
      `Committer` as `color`, per-point tooltip) used by `generate_committer_timeline`,
      `generate_commits_per_weekday_chart` and `generate_commits_per_hour_chart`.
- [x] 2.3 Implement `generate_committer_timeline(data, target_file)` and verify against sample
      `CommitterActivityData` (produced with a stub, not a real repository) that the written file is valid JSON,
      is a valid Vega-Lite specification, and contains one line/committer plus the point- and legend-tooltip
      constructs from design.md.
- [x] 2.4 Implement `generate_commits_per_weekday_chart(data, target_file)` and
      `generate_commits_per_hour_chart(data, target_file)`, including the explicit weekday/hour `sort`-order on the
      x-axis, and verify analogous to 2.3.
- [x] 2.5 Implement `generate_committer_pie_chart(data, target_file)` (`arc`-mark, `joinaggregate`+`calculate`
      `Share`-transform, `.1%`-formatted tooltip) and verify against sample `CommitterActivityData` that the
      written file is valid JSON, is a valid Vega-Lite specification, and contains one slice per committer plus the
      percentage- and legend-tooltip constructs from design.md.
- [x] 2.6 Add `ScriptCollectionTests/test_RepositoryDiagramGenerator.py` covering 2.1-2.5, run with `pytest` and
      verify all tests pass.

## 3. End-to-end verification

- [x] 3.1 Run the exact call-chain from the proposal
      (`RepositoryDiagramGenerator().generate_committer_timeline(RepositoryHistoryAnalyzer().get_git_history_data(repo, GitHistoryScale.Week), target_file)`,
      and the analogous calls for the pie-chart/weekday/hour generators) against a real repository and verify the
      four produced files are valid Vega-Lite specifications.
- [x] 3.2 Render at least one of the four produced specifications with the existing `vl2svg`-tool (already used by
      `ScriptCollectionCore.generate_chart_diagram`) as a manual sanity-check that the specification is accepted by
      a real Vega-Lite compiler, and verify the render succeeds without error (the rendered image itself is not a
      deliverable of this change, see design.md - Non-Goals).
- [x] 3.3 Run `scbuildcodeunits` (build, lint, tests) for the `ScriptCollection`-codeunit and verify it exits with
      code 0.
- [x] 3.4 Determine the resulting project-version with `scshowprojectversion` and add the corresponding
      `Other/Resources/Changelog/v<version>.md`-entry describing this change.
