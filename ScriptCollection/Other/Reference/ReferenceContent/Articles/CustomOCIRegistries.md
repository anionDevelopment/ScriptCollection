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

Nothing to configure beyond the host-setup above: if the two files exist in the configuration-folder of the user who starts the build, they are mounted read-only into the build-container automatically (to `/Workspace/ScriptCollectionConfiguration/OCIImages/ImageRegistries.csv` and `/Workspace/ScriptCollectionConfiguration/TFCPS/EnvironmentVariables.csv`), so the build inside the container resolves both exactly like a build on the host does.

### GitLab-pipeline

Put the two files (or the whole configuration-folder) on the runner-host and mount it into every job-container once, in the runner's `config.toml` - see [Build-runner-configuration](./BuildRunnerConfiguration.md#gitlab) for the exact `volumes`-entry. No repository has to change its `.gitlab-ci.yml` for this.

### GitHub-pipeline

If the self-hosted runner is the `SCGitHubRunner`-codeunit (see [Build-runner-configuration](./BuildRunnerConfiguration.md#github)), set `SCRIPTCOLLECTION_CONFIGURATION_FOLDER` (the absolute path of the configuration-folder **on the runner-host**) once in the runner's `docker-compose.yml`; SCGitHubRunner then mounts it into every job-container it starts. See the "Container-hooks" section of `SCGitHubRunner`'s own usage-documentation. Otherwise (a runner-image you can not extend this way), mount the configuration-folder in `.github/workflows/buildpipeline.yml` as described in [Build-runner-configuration](./BuildRunnerConfiguration.md#github).

## Migration note

Credentials for a custom registry used to be configurable in a separate file, `GlobalCache/RegistryCredentials.csv`. That file has been removed: it only duplicated `TFCPS/EnvironmentVariables.csv` for a single, narrower purpose and needed its own mount everywhere `ImageRegistries.csv` already needed one. If you still have a `RegistryCredentials.csv`, move its entries into `TFCPS/EnvironmentVariables.csv` as `OCIRegistry_<name>_Address` / `_Username` / `_Password` (see above) and delete the file; it is no longer read.
