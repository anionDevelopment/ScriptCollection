# ScriptCollection

## General

[![Supported Python versions](https://img.shields.io/pypi/pyversions/ScriptCollection.svg)](https://pypi.org/project/ScriptCollection/)
![PyPI](https://img.shields.io/pypi/v/ScriptCollection)
![Dependencies](https://img.shields.io/librariesio/github/anionDevevlopment/ScriptCollection)

[![CodeFactor](https://www.codefactor.io/repository/github/anionDevevlopment/scriptcollection/badge/main)](https://www.codefactor.io/repository/github/anionDevevlopment/scriptcollection/overview/main)
[![Downloads](https://pepy.tech/badge/scriptcollection)](https://pepy.tech/project/scriptcollection)
![Coverage](https://raw.githubusercontent.com/anionDevevlopment/ScriptCollection/main/ScriptCollection/Other/Resources/TestCoverageBadges/badge_shieldsio_linecoverage_blue.svg)

The ScriptCollection is the place for reusable scripts.

## Reference

The reference can be found [here](https://aniondev.github.io/ScriptCollectionReference/index.html).

## Hints

Most of the scripts are written in [python](https://www.python.org) 3.

Caution: Before executing **any** script of this repository read the sourcecode of the script (and the sourcecode of all functions called by this function directly or transitively) carefully and verify that the script does exactly what you want to do and nothing else.

Some functions are not entirely available on windows or require common third-party tools. See the [Runtime dependencies](#runtime-dependencies)-section for more information.

When using ScriptCollection it is not required but recommended for better usability to have [epew](https://github.com/anionDev/Epew) installed.

## Get ScriptCollection

### Installation via pip

`pip3 install ScriptCollection`

See the [PyPI-site for ScriptCollection](https://pypi.org/project/ScriptCollection)

### Download sourcecode using git

You can simply git-clone the ScriptCollection and then use the scripts under the provided license.

`git clone https://github.com/anionDevevlopment/ScriptCollection.git`

It may be more easy to pip-install the ScriptCollection but technically pip is not required. Actually you need to git-clone (or download as zip-file from [GitHub](https://github.com/anionDevevlopment/ScriptCollection) the ScriptCollection to use the scripts in this repository which are not written in python.

## Troubleshooting

It is recommended to always use only the newest version of the ScriptCollection. If you have an older version: Update it (e. g. using `pip3 install ScriptCollection --upgrade` if you installed the ScriptCollection via pip). If you still have problems, then feel free to create an [issue](https://github.com/anionDevevlopment/ScriptCollection/issues).

If you have installed the ScriptCollection as pip-package you can simply check the version using Python with the following commands:

```lang-bash
from ScriptCollection.ScriptCollectionCore import ScriptCollectionCore
ScriptCollectionCore.get_scriptcollection_version()
```

Or you can simply run `pip3 freeze` folder to get information about (all) currently installed pip-packages.

## Development

### Branching-system

This repository applies the [GitFlowSimplified](https://projects.aniondev.de/PublicProjects/Common/ProjectTemplates/-/blob/main/Conventions/BranchingSystem/GitFlowSimplified/GitFlowSimplified.md)-branching-system.

### Repository-structure

This repository applies the [CommonProjectStructure](https://projects.aniondev.de/PublicProjects/Common/ProjectTemplates/-/blob/main/Conventions/RepositoryStructure/CommonProjectStructure/CommonProjectStructure.md)-branching-system.

### Install dependencies

ScriptCollection requires [Python](https://www.python.org) 3.10.

To develop ScriptCollection it is obviously required that the following commandline-commands are available on your system:

- `python` (on some systems `python3`)
- `pip3`

The pip-packages which are required for developing on this project are defined in `requirements.txt`.

### IDE

The recommended IDE for developing ScriptCollection is Visual Studio Code.
The recommended addons for developing ScriptCollection with Visual Studio Code are:

- [Pylance](https://marketplace.visualstudio.com/items?itemName=ms-python.vscode-pylance)
- [Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)
- [Spell Right](https://marketplace.visualstudio.com/items?itemName=ban.spellright)
- [docs-markdown](https://marketplace.visualstudio.com/items?itemName=docsmsft.docs-markdown)

### Build

To create and install an ScriptCollection locally simply do the following commands:

```bash
python ./ScriptCollection/Other/Build/Build.py
pip3 install --force-reinstall ./ScriptCollection/Other/Artifacts/Wheel/ScriptCollection-x.x.x-py3-none-any.whl
```

(Note: `x.x.x` must be replaced by the appropriate version-number.)

### Coding style

In this repository [pylint](https://pylint.org/) will be used to report linting-issues.
If you change code in this repository please ensure pylint does not find any issues before creating a pull-request.

If linting-issues exist in the current code-base can be checked by running `python ./ScriptCollection/Other/QualityCheck/Linting.py`.

## Runtime dependencies

ScriptCollection requires [Python](https://www.python.org) 3.10.

The usual Python-dependencies will be installed automagically by `pip`.

For functions to to read or change the permissions or the owner of a file the ScriptCollection relies on the functionality of the following tools:

- chmod
- chown
- ls

This tools must be available on the system where the functions should be executed. Meanwhile this tools are also available on Windows but may have a slightly limited functionality.

## License

See [License.txt](https://raw.githubusercontent.com/anionDevevlopment/ScriptCollection/main/License.txt) for license-information.
