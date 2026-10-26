# Common-Projects-Structure-Findings Specification

## Purpose

Records how findings of code-reviews, security-checks, bug-searches, performance-analyses and similar analyses are documented in a product that uses the common project structure.
Without a single place and a single form for findings, every analysis writes its own list into its own document, the same finding is listed several times under different names, and nobody can tell which findings are still open.

## Requirements

### Requirement: Findings are collected in one table

Every finding of a code-review, a security-check, a bug-search, a performance-analysis or any other analysis of this repository SHALL be recorded in the table of the section `## Findings` in `Other/Reference/Reference.md`.
Findings SHALL NOT be recorded in any other document.
If the section or the table does not exist yet, it SHALL be created.

#### Scenario: An analysis produces findings

- **WHEN** an analysis of this repository produces findings
- **THEN** every finding is added as a row to the table in the section `## Findings` in `Other/Reference/Reference.md`, and no separate list of findings is written anywhere else

#### Scenario: A specification which is not fulfilled is found

- **WHEN** a specification which is not fulfilled by the repository is found, regardless of whether it was found by a targeted check or by chance during any other work or by an audit which checks if all specs are fulfilled
- **THEN** this is added as a finding to the table in the section `## Findings` in `Other/Reference/Reference.md`

#### Scenario: A list of findings is found in another document

- **WHEN** a document of this repository other than `Other/Reference/Reference.md` contains findings
- **THEN** these findings are moved into the table and removed from the place where they were and if that document has no actual content left afterwards, it is deleted together with every reference to it, unless it is `ReadMe.md` of the repository, the `ReadMe.md` of a codeunit, `<codeunit>/Other/Reference/ReferenceContent/Hints.md` or `<codeunit>/Other/Reference/ReferenceContent/index.md`, which stay even when they are empty

### Requirement: Findings have an id with a prefix and an ascending number

Every finding MUST have an id of the form `<prefix>-<ascending number>`.

#### Scenario: The prefix of a new finding is chosen

- **WHEN** a new finding gets a prefix
- **THEN** the prefix is chosen by the first of the following rules which applies:
  1. `SEC` if the finding is relevant for security
  2. `BUS` if the finding is about incorrectly implemented business-logic
  3. `PER` if the finding has an impact on performance
  4. `BUG` if the finding is any kind of bug
  5. `OTH` for every other finding

#### Scenario: The number of a new finding is chosen

- **WHEN** a new finding gets a number
- **THEN** the number is ascending per prefix, written without leading zeros (for example `SEC-1` or `SEC-12`, but not `SEC-01`)
- **AND** the id is never reused for another finding, not even after the finding was fixed

#### Scenario: Existing findings follow another name-pattern

- **WHEN** findings already exist with another name-pattern
- **THEN** they may be renamed to follow the name-pattern specified here

#### Scenario: A new finding is added

- **WHEN** a new finding is added to the table
- **THEN** its prefix is determined by the rules above in their order, and its number is the highest number already used with that prefix plus one

#### Scenario: A finding which already has an id is moved into the table

- **WHEN** a finding which already has an id is moved into the table
- **THEN** its id is kept if possible, and only an id which does not fit the form or which collides with an existing id is replaced by a new one which fits the form

### Requirement: The findings-table has fixed columns

The findings-table MUST have a fixed set of columns in a fixed order.

#### Scenario: The columns of the findings-table

- **WHEN** the findings-table is created or checked
- **THEN** it has exactly these columns in this order:
  - `Id`: the id of the finding
  - `Priority`: the priority of the finding, which is `low`, `mid`, `high` or `very high`
  - `State`: the state of the finding, which is `open`, `accepted`, `not verifiable` or `fixed`
  - `Description`: what the finding is
  - `Impact`: what the finding causes, depending on its topic, for example the security-impact or the performance-impact
  - `Notes`: every further information, especially the content of further columns which a list of findings had before it was moved into the table

#### Scenario: A finding reveals a critical security-problem

- **WHEN** a finding reveals very important or critical security-problems
- **THEN** its `Priority` is marked as `very high`

#### Scenario: A finding reveals a severe performance-problem

- **WHEN** a finding reveals very heavy performance-problems
- **THEN** its `Priority` is marked as `high` or `very high`

#### Scenario: The state of a finding does not fit the standard set

- **WHEN** none of `open`, `accepted`, `not verifiable` or `fixed` applies to a finding
- **THEN** another state is used and the reason for it is written into `Notes`

#### Scenario: A finding is only fixed partially

- **WHEN** an issue is fixed partially
- **THEN** its state is treated as `open`

#### Scenario: An existing table has another structure

- **WHEN** tables already exist with another structure
- **THEN** they may be updated to follow the structure specified here

#### Scenario: A list of findings has further columns

- **WHEN** a list of findings which is moved into the table has columns other than the ones above
- **THEN** the content of these columns is written into `Notes` instead of adding further columns to the table

### Requirement: The state of a finding is determined from the source-code

The state of a finding SHALL be determined by checking the source-code itself, not by documentation or comments.
A fixed finding SHALL NOT be removed from the table; its state SHALL be set to `fixed` instead.
The id of a finding SHALL be struck through for example `~~SEC-2~~` if and only if its state is `fixed`, and no other cell of the table SHALL ever be struck through.

#### Scenario: A finding was fixed

- **WHEN** the source-code shows that a finding is not present anymore
- **THEN** the row stays in the table, its state is set to `fixed` and its id is struck through

#### Scenario: A finding is still present

- **WHEN** the source-code shows that a finding is still present completely or partially
- **THEN** its state is `open` or `partially fixed` and its id is not struck through

### Requirement: The findings-section is formatted

After the findings-section was changed, the whole section SHALL be formatted according to the `format-markdown-file`-skill.

#### Scenario: The findings-table was changed

- **WHEN** a row of the findings-table was added or changed
- **THEN** the whole section `## Findings` is formatted, including the padding of the table-cells
