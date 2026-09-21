# Custom OCI-registries

## Why

A codeunit-build (`scbuildcodeunits`, with or without `-c`) pulls several third-party OCI-images - the base-image of a Dockerfile, the images of local test-services, tools like Syft or Curl. By default these come from their upstream registry (usually [docker-hub](https://hub.docker.com/)), which has a low unauthenticated rate-limit. If you host your own registry that mirrors these images (for example because you already need one for your own products), you want ScriptCollection to prefer it - without having to declare that preference, or the credentials for it, in every single repository that happens to pull an image.

This article describes how to set that up, and how to make it work in every environment `scbuildcodeunits` supports: a Windows host, a Linux host, a local container-build (`scbuildcodeunits -c`), a GitLab-pipeline and a GitHub-pipeline. It ties together two machine-wide configuration-files which are both explained in full in [Configuration-folder](./ConfigurationFolder.md):

- [`GlobalCache/OCIImages/ImageRegistries.csv`](./ConfigurationFolder.md#globalcacheociimagesimageregistriescsv) - maps an image-name to your custom registry.
- [`TFCPS/EnvironmentVariables.csv`](./ConfigurationFolder.md#tfcpsenvironmentvariablescsv) - declares the credentials for that registry (among everything else it declares, see [OCI-registries](./ConfigurationFolder.md#oci-registries)).

Both files live in the same machine-wide configuration-folder (`~/.ScriptCollection`), so everywhere that folder (or the two files below it) is made available, both the registry-mapping and its credentials work together.

## The two files

```text
~/.ScriptCollection/
├── TFCPS/
│   └── EnvironmentVariables.csv
└── GlobalCache/
    └── OCIImages/
        └── ImageRegistries.csv
```

`GlobalCache/OCIImages/ImageRegistries.csv` declares which image is taken from which registry:

```csv
ImageName;RegistryAddress
Debian;commonapplicationimageregistry.aniondev.de/debian
```

`TFCPS/EnvironmentVariables.csv` declares the credentials for that registry. The registry is named freely (`CommonApplicationImageRegistry` below); the name only groups its three values, it does not have to match the address:

```csv
EnvVariableName;Kind;Value
OCIRegistry_CommonApplicationImageRegistry_Address;literal;commonapplicationimageregistry.aniondev.de
OCIRegistry_CommonApplicationImageRegistry_Username;literal;myuser
OCIRegistry_CommonApplicationImageRegistry_Password;file;Secrets/CommonApplicationImageRegistry.txt
```

Unlike a [required environment-variable](./ConfigurationFolder.md#required-environment-variables) of a product, an `OCIRegistry_*`-declaration does **not** have to be repeated per repository: every registry declared this way is available to every build on the machine, because which registries exist is a property of the machine/pipeline, not of a particular product. There is deliberately no separate credentials-file for this (only `EnvironmentVariables.csv`), so the same single mount/copy makes both the required environment-variables of a product and the OCI-registry-credentials available.

With both files in place, `get_registry_address_for_image` (used for every image ScriptCollection resolves, including the base-image of a Dockerfile via its `ARG image_<name>`/`FROM ${image_<name>}` pair) logs in to `commonapplicationimageregistry.aniondev.de` first and then prefers it over the upstream fallback-registry the repository declares - transparently, for every product built on the machine.

## Setup per environment

### Windows host

Create the two files under `%USERPROFILE%\.ScriptCollection\`. `scbuildcodeunits` (without `-c`) reads them directly - nothing else to configure.

### Linux host

Create the two files under `~/.ScriptCollection/`. Same as Windows, `scbuildcodeunits` reads them directly.

### Local container-build (`scbuildcodeunits -c`)

Nothing to configure beyond the host-setup above: `ImageRegistries.csv` and the whole `TFCPS`-folder of the configuration-folder of the user who starts the build are mounted read-only into the build-container automatically (to `/Workspace/ScriptCollectionConfiguration/OCIImages/ImageRegistries.csv` and `/Workspace/ScriptCollectionConfiguration/TFCPS`), so the build inside the container resolves both exactly like a build on the host does. The whole `TFCPS`-folder is mounted (and not only `EnvironmentVariables.csv` in it) so that a `file`-value with a relative path - the recommended form for a secret - also resolves inside the container.

> A value of the kind `hostenvvariable` is the one exception: it names an environment-variable of the machine the command was started on, which by definition does not exist inside the job-container. A registry declared that way is skipped there (with a warning naming the reason) and its images are taken from the fallback-registry. Use `literal` or `file` for a registry which has to work inside a container as well.

### GitLab-pipeline

Put both files on the runner-host (in one folder which has the same structure as `~/.ScriptCollection`, see above) and mount that folder into every job-container once, in the `config.toml` of the runner. [Build-runner-configuration](./BuildRunnerConfiguration.md#gitlab-official-runner-image-docker-executor) shows the `docker-compose.yml` of the runner and the exact `volumes`-entry. No repository has to change its `.gitlab-ci.yml` for this.

### GitHub-pipeline

If the self-hosted runner is the `SCGitHubRunner`-codeunit, set `SCRIPTCOLLECTION_CONFIGURATION_FOLDER` (the absolute path of that folder **on the runner-host**) once in the `docker-compose.yml` of the runner; it then mounts the folder into every job-container it starts, so no repository-workflow has to be changed. With any other runner-image the mount is added to the workflow of the repository instead. [Build-runner-configuration](./BuildRunnerConfiguration.md#github-scgithubrunner) shows both variants.

## If the custom registry is not used

The fallback to the upstream-registry never breaks a build, so an incomplete setup shows up as rate-limits instead of as an error. Every fallback is logged with its reason, so the build-log is the place to look. The usual causes:

- The folder on the runner-host does not contain `GlobalCache/OCIImages/ImageRegistries.csv` - then no image has a custom registry at all. Note that this file has to exist even when it is empty, see [Build-runner-configuration](./BuildRunnerConfiguration.md#folder-on-the-runner-host).
- The credentials can not be resolved in this environment: the registry is then skipped with a warning which names the reason (a secret-file which does not exist there, a `hostenvvariable` which is not set there).
- The image does not exist in the custom registry with the tag the repository declares (`.ScriptCollection/OCIImages/ImageDefinition.csv`) - the mirror does not have that tag yet.
- The build runs with a ScriptCollection-version which does not have this mechanism yet. In a pipeline that version is the one the pipeline installs (`pip3 install scriptcollection --upgrade` as a step of the workflow respectively of `.gitlab-ci.yml`) - without such a step it is the version which is pinned in the job-image.

## Migration note

Credentials for a custom registry used to be configurable in a separate file, `GlobalCache/RegistryCredentials.csv`. That file has been removed: it only duplicated `TFCPS/EnvironmentVariables.csv` for a single, narrower purpose and needed its own mount everywhere `ImageRegistries.csv` already needed one. If you still have a `RegistryCredentials.csv`, move its entries into `TFCPS/EnvironmentVariables.csv` as `OCIRegistry_<name>_Address` / `_Username` / `_Password` (see above) and delete the file; it is no longer read.
