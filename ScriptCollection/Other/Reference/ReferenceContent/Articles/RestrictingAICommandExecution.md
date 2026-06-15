# Restricting AI command-execution with `scruncommandinfolder`

## The problem

When an AI-agent is allowed to execute commands, you usually face an uncomfortable trade-off:

- Either you allow a broad command (for example `dotnet` or `python`) — but then the agent can run it
  with *any* arguments in *any* folder, which is hard to reason about and easy to abuse.
- Or you forbid command-execution entirely — but then the agent can no longer do useful work like
  building, testing or linting.

What you usually *want* is the middle ground: allow a **specific, predefined command** (including its
arguments) that **always runs inside one known folder** (e.g. a single repository), and let the agent only
contribute **a subpath of that folder as an argument** — without ever changing the command, its arguments
or the folder it runs in.

`scruncommandinfolder` is built exactly for this.

## How it works

```text
scruncommandinfolder -b <basefolder> -c <command> -a "<arguments>" [-e <excludedfolder> ...] -f <actualfolder>
```

| Flag | Meaning |
|------|---------|
| `-b` / `--basefolder` | The repository-folder. The command is **always** executed with this folder as its working-directory. `actualfolder` must be this folder or a subfolder of it. |
| `-c` / `--command` | The program to execute (for example `python`, `dotnet`, `git`). |
| `-a` / `--arguments` | The arguments passed to the command. May contain the magic string `{actual_folder}`, which is replaced by the resolved `actualfolder`. |
| `-e` / `--excludedfolder` | A folder that is **forbidden** even though it lies inside `basefolder`. Must be given **relative to** `basefolder`. Can be repeated. If `actualfolder` is equal to or inside one of these, the command is rejected. |
| `-f` / `--actualfolder` | A subpath of `basefolder` that the agent may supply. It is validated and then substituted into the arguments via the placeholder — it does **not** change where the command runs. If it is relative it is resolved against the current working-directory. |

The command itself always runs with `basefolder` as its working-directory; the agent never gets to choose
the folder the command runs *in*. The only thing `actualfolder` does is provide a (validated) path that can
be inserted into the command's arguments.

Before the command is executed, `scruncommandinfolder` resolves `actualfolder` to an absolute path and
verifies that it is equal to `basefolder` or located **inside** it. If it is not, the command is rejected
with an error and nothing is executed. This check cannot be circumvented through relative paths or path
fragments, because the comparison happens on normalized, resolved absolute paths.

## Why this is safe to put into an allow-list

The idea is to put a **fully specified** invocation into the allow-list (for example the allow-file of an
AI-agent's command-permissions) and let the agent only append a subpath of the repository that it wants to
pass as an argument:

```text
scruncommandinfolder -b <repo> -c mycommand -a "my argument {actual_folder} some more arguments" *
```

- `-b <repo>`, `-c mycommand` and the whole `-a "…"` part are **pinned** by the allow-rule. The agent
  cannot change the command, cannot change its arguments, and cannot change the base-folder.
- The trailing `*` is the wildcard of the allow-rule. It permits the agent to append the remaining part of
  the invocation — i.e. `-f <some-subpath>`. So **the only thing the agent gets to choose is a subpath of
  the repository that is passed into the command as an argument** — not where the command runs.
- And even that choice is not free: `scruncommandinfolder` enforces that the supplied `-f`-path lies within
  `<repo>`. The agent can reference a subfolder of the repository, but nothing outside of it. The command
  still always runs with `<repo>` as its working-directory.

### A real allow-file example

The file [`Examples/scruncommandinfolder.claude-settings.example.json`](./Examples/scruncommandinfolder.claude-settings.example.json)
shows how this looks in a Claude-Code `settings.local.json`:

```json
{
  "permissions": {
    "allow": [
      "Bash(scruncommandinfolder -b /work/myrepo -c dotnet -a \"build {actual_folder} --configuration Release\" *)",
      "Bash(scruncommandinfolder -b /work/myrepo -c dotnet -a \"test {actual_folder}\" *)"
    ]
  }
}
```

The important point: `-b /work/myrepo` is part of the **literal prefix** of the allow-rule. The repository
folder is hard-coded into the permission and is **not** something the agent supplies. The agent only gets
to provide the part covered by the trailing `*`, i.e. the `-f <subpath>`-argument. So the repository is the
fixed working-directory of every allowed invocation, and the agent can at most reference a subfolder inside
it as an argument — it can never move the execution out of the repository.

> **Tip: use `.` instead of an absolute path to make the rule portable and committable.**
> Instead of hard-coding an absolute path like `/work/myrepo`, you can set `-b .`:
>
> ```json
> {
>   "permissions": {
>     "allow": [
>       "Bash(scruncommandinfolder -b . -c dotnet -a \"build {actual_folder} --configuration Release\" *)",
>       "Bash(scruncommandinfolder -b . -c dotnet -a \"test {actual_folder}\" *)"
>     ]
>   }
> }
> ```
>
> `.` is resolved against the current working-directory, which is the repository-root when the agent runs
> commands from there (the default). Because the rule no longer contains a machine-specific absolute path,
> it is **identical for every developer and every checkout-location**, so you can commit it and put it into
> the shared `settings.json` (instead of only the personal, git-ignored `settings.local.json`).
>
> Note that with `-b .` the working-directory is "wherever the command is invoked from" rather than a fixed
> absolute path. As long as the agent's working-directory is reliably the repository-root, this is equivalent
> and safe; if the working-directory could be redirected (for example by a chained `cd` in the same
> invocation), an absolute `-b` gives the stronger guarantee.

The net effect is a sharp reduction of what the agent can do, while still letting it do the intended work:

- **defined command** — only `mycommand` with exactly the pinned arguments can run, nothing else,
- **fixed location** — the command **always** runs with `<repo>` as its working-directory; it never runs
  anywhere else,
- **agent-controlled detail** — the agent only selects *which subpath of the repository* is passed to the
  command as an argument.

This increases security precisely because you are allowing *defined* commands, but only *for certain
folders* — instead of handing out a general-purpose command-execution capability.

## The `{actual_folder}` placeholder

Often the command needs to know the folder the agent picked — not as the working-directory, but as an
explicit argument (for example a path to build or a directory to lint). For that, write the magic string
`{actual_folder}` anywhere inside the `-a`-arguments. Every occurrence is replaced with the resolved
absolute path of `actualfolder` right before execution:

```text
scruncommandinfolder -b /work/myrepo -c dotnet -a "build {actual_folder} --configuration Release" -f /work/myrepo/src/MyProject
```

Here the allow-rule pins `dotnet build {actual_folder} --configuration Release`, and the agent only decides
*which* subpath (`src/MyProject`) is passed as the build-target. The command still runs with `/work/myrepo`
as its working-directory — the agent does not pick where `dotnet` runs, only the path-argument it receives.
Because the placeholder is substituted by `scruncommandinfolder` itself (and the path is validated to be
inside `/work/myrepo`), the agent cannot smuggle in a different path or extra arguments through it.

## Excluding folders inside the base-folder

Sometimes a folder lies *inside* the repository but must still be off-limits — for example `.git`, `.claude`
or a folder holding secrets. For these cases there is the `-e` / `--excludedfolder` flag. Each excluded
folder is given **relative to the base-folder** and can be repeated:

```text
scruncommandinfolder -b /work/myrepo -c dotnet -a "test {actual_folder}" -e .git -e .claude -e Other/Secrets -f <subpath>
```

Now `actualfolder` is rejected not only when it lies *outside* the base-folder, but also when it is equal to
or located *inside* any of the excluded folders. So `-f /work/myrepo/.git` or
`-f /work/myrepo/Other/Secrets/keys` both fail, even though they are technically inside the repository.

Two properties make this robust:

- The excluded folders are resolved (relative to the base-folder) and normalized, so a `..`-trick like
  `-f .git/../.git` cannot sneak back into an excluded folder.
- The excluded folders **must be relative**. Passing an absolute path as `-e` is rejected with an error.
  This keeps the meaning unambiguous (always "relative to this repository") and keeps the allow-rule
  portable when `-b .` is used.

In an allow-list, the excluded folders are part of the pinned prefix, just like the command and its
arguments — the agent cannot remove or weaken them:

```json
{
  "permissions": {
    "allow": [
      "Bash(scruncommandinfolder -b . -c dotnet -a \"test {actual_folder}\" -e .git -e .claude -e Other/Secrets *)"
    ]
  }
}
```

## Path-traversal cannot be used to escape the base-folder

A natural attempt to trick the check is to pass an `actualfolder` that *looks* like it is inside the
base-folder but uses `..`-segments to climb back out:

```text
scruncommandinfolder -b /work/myrepo -c dotnet -a "test" -f "/work/myrepo/../../../OtherProject"
```

or, with a relative argument that walks up from the working-directory:

```text
scruncommandinfolder -b /work/myrepo -c dotnet -a "test" -f "../../../OtherProject"
```

Both attempts are **rejected**. Before comparing, `scruncommandinfolder` resolves `actualfolder` to a
normalized absolute path (relative paths are resolved against the current working-directory, and every
`..`-segment is collapsed). The string `"/work/myrepo/../../../OtherProject"` therefore becomes something
like `/OtherProject`, which is neither equal to `/work/myrepo` nor located inside it. The check fails and
the command exits with an error **without executing anything**.

This is why the comparison is done on resolved, normalized paths instead of on the raw strings: a naive
`startswith`-check on the literal text would be fooled by `/work/myrepo/../../../OtherProject` (it *does*
start with `/work/myrepo`), but after normalization the `..`-segments are gone and the real target is
revealed. The actual enforcement happens in `ScriptCollectionCore.run_command_in_folder`, so it holds
regardless of how the command is invoked.

## Related: allow reading any file except in certain folders

The same "allow broadly, but exclude some folders"-idea is useful for **reading** files, too. `scprintfilecontent`
(which prints the content of the file given via `-p`) supports the very same `--excludedfolder` mechanism: you
let the agent read any file in general, but forbid a few sensitive folders. The folders are given with `-x` /
`--excludedfolder`, relative to the base-folder `-b`. The file
[`Examples/scprintfilecontent.claude-settings.example.json`](./Examples/scprintfilecontent.claude-settings.example.json)
shows this:

```json
{
  "permissions": {
    "allow": [
      "Bash(scprintfilecontent -b . -x .git -x .claude -x Other/Secrets -p *)"
    ]
  }
}
```

The pinned prefix `scprintfilecontent -b . -x .git -x .claude -x Other/Secrets` fixes the excluded folders,
and the trailing `*` lets the agent only supply the `-p <file>`-argument. The agent may then read any file —
except files located in `.git`, `.claude` or `Other/Secrets`, which `scprintfilecontent` rejects with an
error.

Note that this is **not** done with fragile `deny`-string-patterns. The exclusion is enforced inside the
command by the same resolved, normalized-path containment-check that `scruncommandinfolder` uses (both share
`ScriptCollectionCore.path_is_inside_one_of_the_folders`). So a `..`-trick or a different path-spelling cannot
be used to read an excluded file — the check operates on the real, resolved target-path, not on the literal
command-string.
