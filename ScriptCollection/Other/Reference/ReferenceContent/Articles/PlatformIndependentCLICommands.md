# Platform-independent CLI commands

## Overview

ScriptCollection ships with a set of small command-line tools that wrap common filesystem and string operations.
The reason they exist as standalone CLI-commands (and not "just" as Python-functions on `ScriptCollectionCore`) is that they make the same operation usable from:

- any shell on **any operating system** (Windows `cmd`/PowerShell, Linux/macOS `bash`/`zsh`, etc.) with **identical syntax**,
- inside Python-code via `ScriptCollectionCore`, which for a part of these operations (see [Counterpart in `ScriptCollectionCore`](#counterpart-in-scriptcollectioncore)) transparently delegates to these commands when the actual execution happens on a **remote/different platform** through the configured `ProgramRunner`.

If you write a build- or maintenance-script with these commands, the same script will run unchanged on Windows, Linux and macOS.

## Commands

### Filesystem queries

| Command | What it does | Exit-codes |
|---------|--------------|------------|
| `scfileexists -p <path>` | Tests whether `<path>` is an existing file. | `0` = exists, `2` = does not exist, `1` = error |
| `scfolderexists -p <path>` | Tests whether `<path>` is an existing folder. | `0` = exists, `2` = does not exist, `1` = error |
| `scgetsize -p <path>` | Prints the size of a file (bytes) to stdout. A relative path is resolved against the current working-directory. | `0` = success, `1` = error (for example the file does not exist) |
| `scprintfilesize -p <path>` | Prints the size of a file (bytes) to stdout. | `0` = success, `1` = error |
| `sclistfoldercontent -p <path> [-f] [-d] [-n] [-t] [--extension <list> \| --glob <pattern> \| --regex <pattern>]` | Lists the entries of a folder. `-f` excludes files, `-d` excludes folders, `-n` prints only names without paths, `-t` recurses into subfolders. The optional filters (mutually exclusive) are matched against the name of the entry: `--extension` takes a comma-separated list of extensions without dot. | `0` = success, `1` = error |

### File reading and writing

| Command | What it does | Exit-codes |
|---------|--------------|------------|
| `scprintfilecontent -p <path>` | Prints the textual content of a file to stdout. | `0` = success, `1` = error |
| `scsetcontentoffile -p <path> -c <content> [--argumentisinbase64]` | Overwrites a file's content. With `--argumentisinbase64` the content is interpreted as base64-encoded UTF-8, which lets you transport arbitrary text (including newlines and quotes) safely on any shell. Binary content is not supported because the decoded bytes must be valid UTF-8. | `0` = success, `1` = error |
| `scfilecontainscontent -p <path> -c <pattern> [-r] [-i] [-e <encoding>]` | Tests whether `<pattern>` occurs in the file. `-r` treats the pattern as regex, `-i` makes the match case-insensitive. | `0` = contains, `2` = does not contain, `1` = error |
| `scappendlinetofile -p <path> -l <line> [--skip-leading-newline-if-file-already-ends-with-newline] [--no-trailing-newline]` | Appends a single line to an existing file. By default a leading newline (only if the file is not empty) and a trailing newline are added so the line is on its own line and the file remains POSIX-line-ended. | `0` = success, `1` = error |
| `scregexreplaceinfile -p <path> -r <pattern> -w <replacement> [-i] [-m] [-d] [-e <encoding>]` | In-place regex replacement on a file. Backreferences (`\1`, `\2`, …) are supported. Flags: `-i` case-insensitive, `-m` multiline, `-d` dotall. | `0` = success, `1` = error |

### File and folder manipulation

| Command | What it does | Exit-codes |
|---------|--------------|------------|
| `sccreatefile -p <path> [--errorwhenexists] [--createnecessaryfolder]` | Creates an empty file. | `0` = success, `1` = error |
| `sccreatefolder -p <path> [--errorwhenexists] [--createnecessaryfolder]` | Creates an empty folder. | `0` = success, `1` = error |
| `scremovefile -p <path> [-e]` | Removes a file. A file which does not exist is not an error unless `-e` (`--errorwhennotexists`) is set. | `0` = success, `1` = error |
| `scremovefolder -p <path> [-e]` | Removes a folder (recursively). A folder which does not exist is not an error unless `-e` (`--errorwhennotexists`) is set. | `0` = success, `1` = error |
| `screname -s <source> -t <target>` | Renames/moves a file or folder. | `0` = success, `1` = error |
| `sccopy -s <source> -t <target>` | Copies a file or folder. Fails if the target already exists. | `0` = success, `1` = error |

### Source-code checks

| Command | What it does | Exit-codes |
|---------|--------------|------------|
| `sccheckpythonast -p <path>` | Checks python-source-files for syntax-errors by parsing them with the `ast`-module (without executing them). `<path>` can be a single file (checked regardless of its extension) or a folder (checked recursively for `*.py`-files). Files with a syntax-error are printed as `<file>:<line>:<column>: <message>` to stderr. | `0` = all valid, `2` = at least one syntax-error, `1` = error |

### Iteration and orchestration

| Command | What it does | Exit-codes |
|---------|--------------|------------|
| `scforeach -f <folder> -c "<command>" [-t] [--include-folders] [--skip-files] [--continue-on-error]` | Runs a command for each entry of a folder. The placeholder `{path}` in the command template is substituted with the entry's absolute path. The command is executed by the shell of the operating system. `-t` walks the folder transitively. By default only file-entries are processed; `--include-folders` adds folders, `--skip-files` excludes files. Without `--continue-on-error` the iteration stops at the first failing command. | `0` = all succeeded, `1` = the folder does not exist or nothing is selected, otherwise the exit-code of the last failing command |

### Environment

| Command | What it does | Exit-codes |
|---------|--------------|------------|
| `scprintosname` | Prints `Windows` or `Linux` (mapped from the running OS). Useful for `if`-branches in cross-platform scripts. On any other operating system nothing is printed to stdout. | `0` = success, `1` = other operating system or error |
| `scprintcurrentworkingdirectory` | Prints the current working directory to stdout. | `0` = success, `1` = error |

## Why platform-independent?

Every one of these commands does something that **already exists** as a shell-built-in or Unix-utility:
copy = `cp`/`copy`, remove = `rm`/`del`, regex-replace = `sed`/`Replace-Inline`, iterate = `find -exec` / `ForEach-Object`, etc.

The problem is that the **syntax and behaviour differ** between Windows `cmd`, PowerShell, `bash` and `zsh`.
The `sc*`-commands provide one syntax that works **everywhere identically**:

```bash
# Same syntax on cmd, PowerShell, bash, zsh, ...
scappendlinetofile -p ./CHANGELOG.md -l "## v1.2.0"
scfilecontainscontent -p ./README.md -c "## Installation" || echo "no install-section"
scregexreplaceinfile -p ./pyproject.toml -r 'version = ".*"' -w 'version = "1.2.0"'
scforeach -f ./projects -t -c "git -C \"{path}\" status -s" --include-folders --skip-files
```

This is especially useful in cases where:

- the same maintenance-script has to run on developer-laptops (mixed OSes) and the CI-runner (Linux container),
- a Taskfile / Makefile needs to call file-operations and stay cross-platform without `if`-branches per OS,
- a Python-program uses `ScriptCollectionCore` to drive operations on a **remote** machine via SSH (or any other `ProgramRunner`); the corresponding `ScriptCollectionCore`-method then runs the matching `sc*`-command over the remote channel transparently.

## Counterpart in `ScriptCollectionCore`

For the filesystem-commands there is a matching `ScriptCollectionCore`-method (`is_file`, `is_folder`, `get_size`, `set_file_content`, `remove`, `rename`, `copy`, `create_file`, `create_folder`, `list_content`).
These methods do the operation **locally** when the `ProgramRunner` is configured for local execution (much faster than spawning the CLI),
and call out to the corresponding `sc*`-command when the configured runner targets a remote/different system.
Other methods with a matching command (for example `get_file_content` or `file_contains_content`) always work on the local filesystem.

```python
sc = ScriptCollectionCore()
# Local: direct file IO. Remote (e.g. via SSH-runner): runs the matching sc*-command over the channel.
if sc.is_file("/etc/hosts"):
    sc.set_file_content("/etc/hosts", new_hosts_content)
```

## Combined example

A small "release-prep" workflow that works on any OS, from any shell:

```bash
# Bump version in two files
scregexreplaceinfile -p pyproject.toml -r 'version = ".*"' -w 'version = "1.4.0"'
scregexreplaceinfile -p src/Version.txt -r '.+' -w '1.4.0'

# Append changelog entry
scappendlinetofile -p CHANGELOG.md -l "## v1.4.0 - Build performance improvements" --skip-leading-newline-if-file-already-ends-with-newline

# Verify
scfilecontainscontent -p CHANGELOG.md -c "v1.4.0" && echo "changelog updated"
```
