---
name: product-knowledge
description: What ScriptCollection is, how this repository is structured and which mechanisms exist for building and testing it. Use this before fixing a defect or developing a feature in this repository, to know where things belong and how to verify a change.
---

# ScriptCollection

ScriptCollection is the place for reusable scripts. It is published as the python-package `scriptcollection`,
and it is the implementation behind the "common project structure": the build-scripts of all those
repositories are thin wrappers which delegate to this package.

That makes this repository the one with the widest blast-radius of all: a change here changes how **every**
other repository builds. A defect which slips through is noticed in twenty repositories at once - which is
exactly what happened when the api `TasksForCommonProjectStructure` was removed and about 194 scripts stopped
working.

## Structure of the repository

The repository follows the common project structure itself. Use the
`work-with-common-project-structure`-skill for the details of that structure.

The code-unit is `ScriptCollection`, built as a wheel. Its two halves:

- `ScriptCollectionCore.py` and the modules beside it - the general functions (running programs, git, files,
  images, certificates, ...).
- `TFCPS/` - the implementation of the build-pipeline. `TFCPS_CodeUnitSpecific_<Type>` (DotNet, Docker,
  Python, NodeJS, Flutter, Maven) is what a `Build.py`, `CommonTasks.py`, `Linting.py` and `RunTestcases.py`
  of a code-unit calls; `TFCPS_Tools_General` holds what is independent of the type.

`Executables.py` declares every commandline-command (`scbuildcodeunits`, `scshowprojectversion`,
`scruncommandinfolder`, ...). A new command is added there **and** in the `project.scripts`-section of the
`pyproject.toml`; a command which is declared in only one of the two places does not work.

## What to keep in mind when changing the pipeline

- The pipeline must be idempotent: running it must not change a file which is not git-ignored. Whoever adds a
  generation-step has to make sure its result is either stable or ignored.
- What a code-unit-type-specific class expects from a code-unit is a contract with every repository. When it
  changes (a new mandatory file, a different location, a renamed function), the repositories have to be
  ported - and there are many of them, so prefer a change which keeps the old shape working.
- The version of a project does not come from GitVersion anymore. Use `get_version_of_project`.

## Deploying a change locally

The wheel is built by `scbuildcodeunits` (or `task bb`) into
`ScriptCollection/Other/Artifacts/BuildResult_Wheel`. Since the installed package is what all other
repositories use while you work on them, a change is only visible for them after that wheel is installed.

## Testing

The testcases are in `ScriptCollectionTests` and run with pytest. They test the pure functions directly; what
needs a program (git, docker, ...) is either mocked or tested through a temporary folder.

A testcase must not depend on the machine: no assumption about an installed tool, a locale, a timezone or an
existing path unless the function under test really requires it.
