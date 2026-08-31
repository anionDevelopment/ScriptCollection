## Purpose

Turns a repository's git history into structured committer-activity-data and into ready-to-use Vega-Lite
diagram-specifications, so contribution-patterns become visible without hand-writing git-parsing or charting code.

## ADDED Requirements

### Requirement: Committers are derived from `git shortlog -n -s`
A "committer" SHALL be exactly an identity as `git shortlog -n -s` reports it for the repository (name, and its
descending-by-commit-count ordering). No separate author/committer distinction SHALL be introduced.

#### Scenario: Repository with several contributors
- **WHEN** the history of a repository with several contributors is analyzed
- **THEN** the resulting committer-list contains exactly the identities and the order that `git shortlog -n -s`
  would report for that repository

### Requirement: Each committer's email-address is resolvable
For every committer produced by the analysis, an associated email-address SHALL be resolvable.

#### Scenario: Committer has a recorded email-address
- **WHEN** the history is analyzed and a committer has at least one commit with a recorded email-address
- **THEN** that committer's email-address is part of the analysis-result

### Requirement: Commit-activity can be aggregated per calendar period
Commit-activity SHALL be aggregable per committer and per calendar period, at a selectable granularity of day,
week (calendar week) or year.

#### Scenario: Weekly granularity
- **WHEN** commit-activity is requested with week-granularity
- **THEN** the result contains, for every committer and every calendar week in which that committer has at least
  one commit, the number of commits that committer made in that calendar week

#### Scenario: Daily or yearly granularity
- **WHEN** commit-activity is requested with day-granularity or with year-granularity
- **THEN** the result is aggregated per calendar day respectively per calendar year instead of per calendar week,
  analogous to the weekly case

### Requirement: Commit-activity can be aggregated per weekday
Commit-activity SHALL be aggregable per committer and per weekday (Monday through Sunday), independent of calendar
period.

#### Scenario: Commits distributed across weekdays
- **WHEN** commit-activity per weekday is requested for a repository whose commits span several weekdays
- **THEN** the result contains, for every committer and every weekday on which that committer has at least one
  commit, the number of commits that committer made on that weekday, summed across the whole analyzed history

### Requirement: Commit-activity can be aggregated per hour of day
Commit-activity SHALL be aggregable per committer and per hour of day (00 through 23), independent of calendar
period.

#### Scenario: Commits distributed across hours
- **WHEN** commit-activity per hour of day is requested for a repository whose commits span several hours
- **THEN** the result contains, for every committer and every hour on which that committer has at least one
  commit, the number of commits that committer made in that hour, summed across the whole analyzed history

### Requirement: A committer-timeline diagram-specification can be generated
From per-calendar-period commit-activity-data, a Vega-Lite diagram-specification for a line-diagram SHALL be
generatable, with one line per committer, the calendar period on the x-axis (one point per period present in the
data, at the granularity the data was aggregated with) and the commit-count on the y-axis.

#### Scenario: Timeline for several committers
- **WHEN** a committer-timeline diagram-specification is generated from commit-activity-data of several committers
- **THEN** the generated specification is a valid Vega or Vega-Lite specification which renders one line per
  committer, plotting that committer's commit-count over the calendar periods present in the data

#### Scenario: Hovering a data-point shows its exact commit-count
- **WHEN** a viewer of the rendered timeline-diagram hovers a data-point of a committer's line
- **THEN** a tooltip shows the exact commit-count that data-point represents

### Requirement: A committer pie-chart diagram-specification can be generated
From commit-activity-data, a Vega-Lite diagram-specification for a pie-chart SHALL be generatable, showing each
committer's share of the total commit-count.

#### Scenario: Pie-chart for several committers
- **WHEN** a committer pie-chart diagram-specification is generated from commit-activity-data of several
  committers
- **THEN** the generated specification is a valid Vega or Vega-Lite specification which renders one slice per
  committer, sized by that committer's share of the total commit-count

#### Scenario: Hovering a slice shows its exact percentage
- **WHEN** a viewer of the rendered pie-chart hovers a committer's slice
- **THEN** a tooltip shows that committer's exact percentage-share of the total commit-count

### Requirement: A commits-per-weekday diagram-specification can be generated
From per-weekday commit-activity-data, a Vega-Lite diagram-specification SHALL be generatable, showing each
committer's commit-count per weekday, analogous to the committer-timeline diagram.

#### Scenario: Weekday-diagram for several committers
- **WHEN** a commits-per-weekday diagram-specification is generated from per-weekday commit-activity-data of
  several committers
- **THEN** the generated specification is a valid Vega or Vega-Lite specification which renders, per committer,
  the commit-count for each weekday, and hovering a data-point shows its exact commit-count

### Requirement: A commits-per-hour diagram-specification can be generated
From per-hour commit-activity-data, a Vega-Lite diagram-specification SHALL be generatable, showing each
committer's commit-count per hour of day, analogous to the committer-timeline diagram.

#### Scenario: Hour-of-day-diagram for several committers
- **WHEN** a commits-per-hour diagram-specification is generated from per-hour commit-activity-data of several
  committers
- **THEN** the generated specification is a valid Vega or Vega-Lite specification which renders, per committer,
  the commit-count for each hour of day, and hovering a data-point shows its exact commit-count

### Requirement: Hovering a committer's name reveals their email-address
In every generated diagram-specification (timeline, pie-chart, weekday-diagram, hour-of-day-diagram), hovering the
name of a committer (as shown in the diagram's legend) SHALL reveal that committer's email-address in a tooltip.

#### Scenario: Hovering a legend entry
- **WHEN** a viewer of a rendered diagram hovers a committer's name in the diagram's legend
- **THEN** a tooltip shows that committer's email-address

### Requirement: Diagram-generation produces a specification, not a rendered image
Generating a diagram SHALL produce a Vega or Vega-Lite diagram-specification (as data/text). Rendering that
specification into an image (for example SVG or PNG) is NOT part of this capability.

#### Scenario: Diagram-generation is requested
- **WHEN** any of the four diagram-generation operations is invoked
- **THEN** the outcome is a Vega or Vega-Lite diagram-specification, and no image-file is required to be produced
  by that operation
