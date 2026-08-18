# Architecture Specification

## Purpose

Records the architectural constraints which every change to this product has to respect. They are not derivable from the
source-code itself: they state what decides whether the product is in a healthy state and how the codeunits of this repository may
depend on each other.

## Requirements

### Requirement: "scbuildcodeunits" is the single source of truth for the state of the pipeline

The command `scbuildcodeunits` SHALL always be executable in this repository, and it SHALL succeed whenever the repository
is in a healthy state. Whether the pipeline of this product is green SHALL be decided by that command and by nothing else.

#### Scenario: A change is considered finished

- **WHEN** a change is considered finished
- **THEN** `scbuildcodeunits` has been executed on it and has succeeded

#### Scenario: Another tool reports a different result

- **WHEN** an IDE, a single manually executed step or any other tool reports a result which differs from the result of
  `scbuildcodeunits`
- **THEN** the result of `scbuildcodeunits` is the one which counts, and the deviation is treated as a defect of the other
  tool or of its configuration

### Requirement: A codeunit only accesses codeunits which it declares as its dependencies

A codeunit SHALL NOT access the source-code of another codeunit unless that other codeunit is declared as a dependent
codeunit in its `<codeunit-name>.codeunit.xml`. The codeunits of this repository are: ScriptCollection.

#### Scenario: A codeunit needs functionality of another codeunit

- **WHEN** a codeunit needs functionality which another codeunit of this repository provides
- **THEN** that other codeunit is declared under `dependentcodeunits` in the codeunit-file, and its functionality is used
  through its build-result instead of through its source-code

#### Scenario: An undeclared access exists

- **WHEN** a codeunit reads, includes, compiles or references source-code of a codeunit which is not declared as its
  dependency
- **THEN** this is a defect, which is resolved either by declaring the dependency or by removing the access
