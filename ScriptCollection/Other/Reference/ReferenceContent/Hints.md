# Hints

## Requirements

The following requirements from the [tools-list](https://github.com/anionDevevlopment/ScriptCollection/blob/main/ScriptCollection/Other/Reference/ReferenceContent/Articles/RequirementsForCommonProjectStructure.md#Tools) are required to build and run this code-unit:

- `coverage`
- `docfx`
- `git`
- `python`
- `reportgenerator`
- `scriptcollection`
- `vl2svg`

To create a release the following tools are also required:

- `gh`
- `twine`

## IDE

The recommended IDE for this code-unit is [Visual Studio Code](https://code.visualstudio.com/).

It is recommended to enabled word-wrap.

## Secret-scan of OCI-images

### Why an own scan is required

The secret-scan of the repository-content (betterleaks) can not find secrets which end up in a built image. There are three independent reasons for that:

1. betterleaks does not look into archives. The image-artifacts are `*.tar`-files, so their content is skipped completely.
2. The default-ruleset detects provider-specific token-formats, but not the credential-shapes which occur when dependencies are installed (basic-auth inside an url, a generic `--password`-argument).
3. A part of the secrets is not a file at all: build-arguments, environment-variables and labels are stored in the image-metadata, not in the repository.

An image is published to a registry. Everybody who is allowed to pull it can read these secrets - for the metadata not even a pull is necessary, `docker history` is enough. Therefore the images are scanned separately.

### How a secret gets into an image

There are three ways, which have to be distinguished because they have different consequences:

- **Image-metadata.** A value passed via `--build-arg` is recorded in the `created_by`-entry of every layer built while the argument was in scope (visible as the `|<n> Name=Value …`-prefix), and a value assigned via `ENV` is stored permanently in the image-configuration. Both are part of the image-metadata and are therefore published together with the image.
- **Layer-content.** A file which is written during the image-build stays in its layer. Deleting it in a later instruction does **not** remove it, because the earlier layer remains part of the image. This is what happens when a package-manager writes credentials into a configuration-file (`pip.conf`, `NuGet.Config`, `.npmrc`, `.netrc`) or when a private key is copied into the image.
- **Outside of the image.** The value is also visible in the process-list of the build-host and in the build-log. This is not covered by the scan; it is the reason why secrets should be passed via `RUN --mount=type=secret` instead of `--build-arg`.

### What is scanned

The scan is implemented in `TFCPS_OCIImageSecretScan`. It exports the image with `docker save` and analyses the resulting archive:

| Part | Checked for |
|---|---|
| image-history (`created_by`), environment-variables, labels | private keys, credentials inside an url, assignments whose name indicates a secret (`…Password=…`, `…Token=…`, …) |
| content of the files of every layer | private keys, credentials inside an url |

The name-based heuristic is deliberately **not** applied to the content of the layer-files: a base-image contains thousands of translation-resources and sample-configurations in which a word like `Password` is a label and not a secret, which would drown the real findings in false positives.

Only files whose name indicates credentials (`*.key`, `*.pfx`, `.npmrc`, `pip.conf`, …) or whose extension indicates configuration are read, and only their first megabyte, so the scan stays fast (a few seconds per gigabyte).

A finding never contains the secret itself, because the findings are written to the build-log: passwords inside an url are masked and an assignment is reported by its name only.

### Allowlisting

Known false positives are allowlisted in the `[[allowlists]]`-entries of `<repository>/.betterleaks.toml`, the same file which is used for the repository-scan. The `paths`- and `regexes`-entries are applied to the finding, so the path of the file inside the layer can be used to allowlist it.

### Checking an image manually

`scsearchforsecretsinimage` scans any image which is available in the local docker-instance:

```cmd
scsearchforsecretsinimage -i myimage:1.0.0
scsearchforsecretsinimage -i myimage:1.0.0 -r C:\Repositories\MyProduct
```

The optional `-r` names a repository whose `.betterleaks.toml` is used as allowlist.

Exit-codes:

| Exit-code | Meaning |
|---|---|
| 0 | no error occurred and no secret was found |
| 1 | no error occurred and at least one secret was found |
| 2 | an error occurred (for example the image is not available locally), so the result is unknown |

The distinction between 1 and 2 matters: "no secret found" and "the scan could not be performed" must not be treated the same way by a caller.

During `scbuildcodeunits` the same function is called automatically for every image built by a codeunit of the repository; a finding lets the build fail.
