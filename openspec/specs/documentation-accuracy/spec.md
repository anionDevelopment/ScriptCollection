# Documentation-Accuracy Specification

## Purpose

Records that the documentation of this repository which describes the current state of the product has to agree with what the
source-code actually does, and that this agreement is re-established whenever the specifications of this repository are checked.
This is not derivable from the source-code itself: a document which describes an older state of the product is still a
syntactically valid document, and neither the compiler nor the pipeline notices it. Without this specification a reader can not
decide whether a sentence of the documentation is a fact about the product or a leftover of a state which does not exist anymore,
which makes the whole documentation unusable as a source of information.

## Requirements

### Requirement: Documentation which describes the current state agrees with the source-code

Every document of this repository which describes the current state of the product SHALL describe it the way the source-code of
the current branch implements it. The documents which this applies to are at least:

- `ReadMe.md` in the repository-root
- the `ReadMe.md` of every codeunit (the codeunits of this repository are: ScriptCollection)
- `Contributing.md`
- everything below `Other/Reference`
- everything below `<codeunit>/Other/Reference/ReferenceContent`, especially `Hints.md`, `HowToBuild.md` and the articles
- the doc-comments in the source-code

#### Scenario: A document states something which the source-code does not do

- **WHEN** a document states a behaviour, a feature, a limitation, a default-value, a name or a path which the source-code does
  not implement that way
- **THEN** this is a defect of the same weight as a defect in the source-code, and it is resolved by correcting the document to
  the state which the source-code implements

#### Scenario: The documented state is the wanted state and the source-code is the wrong side

- **WHEN** the document describes what the product is supposed to do and the deviation is a defect of the source-code and not of
  the document
- **THEN** the document stays as it is and the deviation is reported as a defect of the source-code, because rewriting the
  document would hide that defect instead of documenting the product

### Requirement: Lists of features state the implemented state

Every list of features, capabilities, supported formats, supported platforms or supported options SHALL state for every entry
whether it is implemented, and that statement SHALL be the one which the source-code implements. An entry which is not
implemented SHALL stay in the list and be marked as not implemented instead of being removed, so that the list keeps working as
an overview of what is planned.

#### Scenario: A feature became implemented

- **WHEN** a feature which the documentation marks as not implemented - for example with "❌", with "planned", with "not
  implemented yet" or with a link to its issue - is implemented in the source-code
- **THEN** its entry is changed to the marking which this repository uses for an implemented feature, in the same shape as the
  other implemented entries of that list

#### Scenario: A feature was removed or never existed

- **WHEN** a feature which the documentation marks as implemented does not exist in the source-code
- **THEN** its entry is corrected, so that no reader expects a function which the product does not have

#### Scenario: A feature exists but is not listed

- **WHEN** the source-code implements a feature which such a list does not contain although the list claims to be complete for
  its topic
- **THEN** the feature is added to the list

### Requirement: Lists of bugs, findings and technical debts contain only entries which still exist

Every list of known bugs, known limitations, security-findings, technical debts or open points SHALL contain only entries which
still exist in the source-code, and every entry SHALL describe the state which the source-code has now.

#### Scenario: A documented finding was fixed

- **WHEN** a bug, a finding or a technical debt which such a list contains is not present in the source-code anymore
- **THEN** its entry is removed from that list, so that nobody spends time on a problem which does not exist anymore

#### Scenario: A documented finding is still open but changed

- **WHEN** an entry of such a list is still present in the source-code, but the source-code changed in a way which makes the
  description, the named location or the named severity of the entry wrong
- **THEN** the entry stays and its description is corrected

### Requirement: Instructions and references of the documentation resolve

Every command, task, path, file-name, class-name, configuration-key and cross-reference which a document names SHALL exist and
SHALL work in the state of the repository which that document belongs to.

#### Scenario: A document names something which does not exist

- **WHEN** a document names a file, a folder, a command, a task, a class or a configuration-key which does not exist or which was
  renamed
- **THEN** the document is corrected to the name which exists, or the statement is removed if the named thing does not exist
  anymore at all

### Requirement: Checking the specifications includes checking this documentation

Whenever it is checked whether the specifications of this repository are still up to date, the documents named in this
specification SHALL be checked against the source-code in the same run, and every deviation which is found SHALL be corrected in
that run.

#### Scenario: The specifications are checked

- **WHEN** it is checked whether the specifications below `openspec/specs` still agree with the source-code
- **THEN** the documents named in this specification are checked against the source-code as well and the deviating ones are
  adjusted, so that after such a check the documentation is up to date and not only the specifications

#### Scenario: A change is considered finished

- **WHEN** a change of the source-code is considered finished
- **THEN** the documents which describe what that change touched have been updated together with it and not in a later separate
  step

### Requirement: Documents which record the past are not adjusted

A document which records what was true at a point in time SHALL NOT be adjusted to the current state. This applies to the
changelog-files below `Other/Resources/Changelog`, to the log-files below `Other/Logs` and to the archived changes below
`openspec/changes/archive`.

#### Scenario: A record of the past does not describe the current state

- **WHEN** an entry of a changelog, of a log-file or of an archived change describes a state which the product does not have
  anymore
- **THEN** the entry stays unchanged, because it documents what was true when it was written, and changing it would destroy the
  history instead of documenting the product
