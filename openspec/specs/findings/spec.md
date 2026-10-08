# Findings Specification

## Purpose

Records where and how the findings of this repository are managed.
Findings are produced by code-reviews, security-checks, bug-searches, performance-analyses, technical-debt-analyses and similar checks.
When every check writes its findings into the document it happens to work on, the findings end up spread over readmes, articles and separate report-files, nobody has an overview of what is still open, and a fixed finding can not be distinguished from an open one.
This specification defines one single place and one single format for all of them.

## Requirements

### Requirement: All findings are collected in one table

Every finding of this repository SHALL be recorded in the table of the section `## Findings` in `Other/Reference/Reference.md`.
A finding SHALL NOT be recorded in any other document, for example in a `ReadMe.md`, in an article or in a separate report-file.
Other documents MAY link to that section instead.

#### Scenario: A check produces new findings

- **WHEN** a code-review, a security-check, a bug-search, a performance-analysis or a similar check finds something
- **THEN** every finding is added as a row to the table in `Other/Reference/Reference.md` in the section `## Findings`, and the section is created if it does not exist yet

#### Scenario: A finding is found in another document

- **WHEN** a document other than `Other/Reference/Reference.md` contains a finding or a list of findings
- **THEN** the finding is moved into the table and removed from that document
- **AND** a document which has no content anymore afterwards is deleted together with all references to it, except `ReadMe.md` in the repository-root, the `ReadMe.md` of a codeunit and the files `Hints.md` and `index.md` in `<codeunit>/Other/Reference/ReferenceContent`, which stay

### Requirement: The table has a defined set of columns

The table SHALL have exactly the columns `Id`, `State`, `Description`, `Impact` and `Notes`, in this order.

- `Id`: a unique identifier of the finding. An existing id of a finding SHALL be kept. A finding without an id gets a new one which fits to the existing ids (for example `Sec-01` for a security-finding).
- `State`: the state of the finding, for example `Open`, `Partially fixed` or `Fixed`.
- `Description`: what the finding is.
- `Impact`: the effect of the finding, depending on its topic (for example the security- or the performance-impact).
- `Notes`: every further information, including the content of any other column a finding had in its original source.

#### Scenario: A finding has more information than the columns provide

- **WHEN** a finding has further attributes like a severity, a location, a category or a proposed fix
- **THEN** these are written into the column `Notes` and no further column is added

### Requirement: The state of a finding is determined from the source-code

The state of a finding SHALL be determined by checking the source-code itself and not by trusting documentation or comments.

#### Scenario: The state of the findings is updated

- **WHEN** the findings-table is updated
- **THEN** the state of every finding is verified directly in the source-code and corrected if it changed

### Requirement: Fixed findings stay in the table

A fixed finding SHALL NOT be removed from the table.
It SHALL be marked with the state `Fixed` instead, and only then its id SHALL be struck through (for example `~~Sec-02~~`).
No other cell of the table SHALL be struck through.

#### Scenario: A finding was fixed

- **WHEN** the source-code shows that a finding does not exist anymore
- **THEN** its state is set to `Fixed` and its id is struck through, while the row itself and all its other cells stay unchanged

#### Scenario: A finding is not fixed

- **WHEN** a finding is open or only partially fixed
- **THEN** its id is not struck through

### Requirement: The findings-section is formatted

The section `## Findings` SHALL be formatted according to the format-markdown-file-skill, especially with equally padded table-cells per column.

#### Scenario: The findings-table was changed

- **WHEN** a row of the findings-table was added or changed
- **THEN** the whole section `## Findings` is formatted again
