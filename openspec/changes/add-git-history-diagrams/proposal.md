## Why

There is currently no reusable way to turn a repository's git history into a visual overview. Understanding who
contributed when, how contribution-activity is distributed between committers, or when commits typically happen
(weekday/hour) today requires manually running and interpreting several different `git`-commands. A small,
reusable pair of classes that turns the git history into ready-to-use Vega-Lite diagram-specifications closes this
gap and lets other codeunits/scripts of this repository (and consumers of the `ScriptCollection`-package) generate
such diagrams without duplicating git-parsing logic.

## What Changes

- Add `RepositoryHistoryAnalyzer`, a class which reads the git history of a repository and returns structured
  committer-activity-data (who committed how much, when, on which weekday and at which hour of day).
- Add `RepositoryDiagramGenerator`, a class which turns that structured data into Vega-Lite
  diagram-specifications (JSON) for four diagram types: a committer-timeline (line-chart), a committer pie-chart, a
  commits-per-weekday chart and a commits-per-hour chart.
- Add the `GitHistoryScale` enum (`Day`, `Week`, `Year`) which controls the granularity of the timeline-diagram's
  x-axis.
- "Committer" is defined, for both classes, exactly as the identities `git shortlog -n -s` lists (name and
  ordering), i.e. no separate author/committer distinction is introduced.
- Every generated diagram-specification lets a viewer hover a data-point to see its exact value (commit-count or,
  for the pie-chart, percentage) and hover a committer's name (legend) to see that committer's email-address, via
  Vega-Lite tooltip/legend-encoding constructs.
- Generating an actual image (SVG/PNG/...) from a produced Vega-Lite specification is explicitly out of scope of
  this change; the two new classes only produce the diagram-specification (JSON) file. Rendering it is left to the
  already-existing `ScriptCollectionCore.generate_chart_diagram` (or any other Vega-Lite renderer) as a later,
  separate step.

## Capabilities

### New Capabilities
- `git-history-diagrams`: Analyzing a repository's git history into committer-activity-data and generating
  Vega-Lite diagram-specifications (committer-timeline, committer pie-chart, commits-per-weekday,
  commits-per-hour) from that data.

### Modified Capabilities
- (none)

## Impact

- New source files in the `ScriptCollection`-codeunit (`ScriptCollection/ScriptCollection/RepositoryHistoryAnalyzer.py`
  and `ScriptCollection/ScriptCollection/RepositoryDiagramGenerator.py`), plus corresponding unit-tests.
- No new third-party dependency: the git history is read via `git` (already a required tool of this repository) and
  the diagram-specification is plain JSON built with the Python standard library.
- No changes to any existing public API/behavior of `ScriptCollectionCore` or other existing classes.
