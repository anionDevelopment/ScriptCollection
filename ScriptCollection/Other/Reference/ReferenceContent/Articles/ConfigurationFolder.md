# Configuration-folder

## Overview

ScriptCollection reads its machine-wide configuration from the folder `~/.ScriptCollection` (the `.ScriptCollection`-folder in the current user's home-directory).
The folder is created automatically when needed; all configuration-files inside it are optional and only take effect when they exist.

> Note: `~/.ScriptCollection` is the **user-/machine-wide** configuration-folder. It must not be confused with the **per-repository** folder `<repository>/.ScriptCollection`, which contains repository-specific data (see [Per-repository configuration](#per-repository-configuration) below).

Structure of `~/.ScriptCollection`:

```text
~/.ScriptCollection/
├── PythonExecutable.txt
├── DockerExecutable.txt
├── OCR/
│   └── ServiceURL.txt
├── TFCPS/
│   ├── EnvironmentVariables.csv
│   ├── CustomPreCodeUnitBuildScript.py
│   ├── CustomPreCodeUnitBuildScriptForContainer.py
│   └── CustomPreCodeUnitBuildScriptInContainer.py
└── GlobalCache/
    ├── Tools/                          # downloaded tools (see DownloadableTools.md)
    ├── OCIImages/
    │   └── ImageRegistries.csv
    ├── RegistryCredentials.csv
    └── TranslationServiceProperties.txt
```

## Executables

### `PythonExecutable.txt`

Configures which Python-executable ScriptCollection uses. The file-content is the absolute path to the executable. If the file does not exist, the current `sys.executable` (or `python`) is used.

```text
/opt/venv/bin/python
```

### `DockerExecutable.txt`

Configures which Docker-executable ScriptCollection uses. The file-content is the absolute path to the executable. If the file does not exist, the default (`docker`) is used.

```text
/usr/bin/docker
```

## GlobalCache

The folder `~/.ScriptCollection/GlobalCache` is the machine-wide cache. It can be emptied with the command `sccleantoolscache`.

### `GlobalCache/Tools`

Contains the downloaded tools (CycloneDX-CLI, PlantUML, MediaMTX, ...). This folder is managed automatically and can be pre-filled with the command `scdownloadcachabletools`. See [Downloadable tools](./DownloadableTools.md) for details.

### `GlobalCache/OCIImages/ImageRegistries.csv`

When you use third-party OCI-images (for example a base-image for your custom image or a database-image for integration-tests) then you need to take them from a registry.
By default the [docker-hub](https://hub.docker.com/) is used, which has a low rate-limit. It is therefore recommended to host your own registry that caches these images, so they can be pulled without rate-limits.

This file maps an image-name to the custom registry-address it should be taken from. Columns: `ImageName;RegistryAddress`.

```csv
ImageName;RegistryAddress
Debian;myownregistry1.example.com/debian
Nginx;myownregistry1.example.com/nginx
DotNet;myownregistry2.example.com/dotnetbase
```

When a custom registry is defined for an image here, that registry is used. Otherwise the fallback (upstream) registry from the repository's image-definition (see [Per-repository configuration](#per-repository-configuration)) is used.
The purpose of the fallback is that a freshly cloned project just works without further setup; a warning is shown when the fallback-registry is used.

### `GlobalCache/RegistryCredentials.csv`

Optional basic-auth-credentials for registries. Columns: `RegistryName;Username;Password`.

```csv
RegistryName;Username;Password
myregistry1.example.com;user;pa$$w0rD1
myregistry2.example.com;user1;pa$$w0rD2
myregistry2.example.com;user2;pa$$w0rD3
```

### `GlobalCache/TranslationServiceProperties.txt`

Configures the translation-service used to translate XLF-files (for the NodeJS-/web-codeunits). Without this file no automatic translation is done.

```text
LibreTranslateAPI=https://my-libretranslate.example.com
```

## OCR

### `OCR/ServiceURL.txt`

Configures the base-address of the OCR-service used by the OCR-commands (for example `scocranalysisoffile`). The first non-empty, non-comment line (lines starting with `#` are ignored) is used as the service-address.

```text
https://my-ocr-service.example.com
```

## TFCPS

### `TFCPS/EnvironmentVariables.csv`

Defines where the values of the environment-variables come from which a repository declares as required for its build (see [Required environment-variables](#required-environment-variables) below). Because the values are machine-/user-specific (and often secret) they are configured here and not in the repository. Columns: `EnvVariableName;Kind;Value`.

`Kind` is one of:

- `literal`: `Value` is the value of the environment-variable itself.
- `hostenvvariable`: `Value` is the name of an environment-variable which must be set on this system; its value is used.
- `file`: `Value` is a path (`~` is expanded, relative paths are resolved against `~/.ScriptCollection/TFCPS`) to a text-file whose content (without surrounding whitespace) is used.

```csv
EnvVariableName;Kind;Value
MyLiteralVariable;literal;MyValue
MyHostVariable;hostenvvariable;MY_HOST_ENV_VARIABLE
MySecretVariable;file;~/.pp/MySecretVariable.txt
```

The file may contain entries for all repositories built on this machine; only the variables which the currently built repository declares as required are resolved and set.

#### Package-sources

A package-source which is not publicly available (for example a private NuGet-feed) is configured with the same mechanism, because a package-source and especially its credentials must not be part of a repository. A source named `<sourcename>` for the technology `<technology>` (currently `CSharp`) is defined by these environment-variables:

| Environment-variable | Meaning |
|---|---|
| `Dependency_<technology>_<sourcename>_URL` | the url of the source (this variable declares the source) |
| `Dependency_<technology>_<sourcename>_Username` | the username, if the source requires authentication |
| `Dependency_<technology>_<sourcename>_Password` | the password or token belonging to the username |

```csv
EnvVariableName;Kind;Value
Dependency_CSharp_MyPrivateFeed_URL;literal;https://example.com/api/v4/projects/1/packages/nuget/index.json
Dependency_CSharp_MyPrivateFeed_Username;literal;myuser
Dependency_CSharp_MyPrivateFeed_Password;file;~/.secrets/MyToken.txt
```

A repository which needs such a source declares these variable-names as [required environment-variables](#required-environment-variables). Every .NET-codeunit-operation (build, testcases, linting, dependency-update) then registers the declared sources before it resolves the dependencies:

- If a source with the same url is already registered (which is usually the case on a machine on which the developer configured the feed manually), its credentials are updated instead of registering the same feed a second time.
- Sources which are not declared are never removed or changed: the registration is stored in the NuGet-configuration of the current user, which on a developer-machine is the configuration they also use for their own work.
- Inside the build-container the source is registered the same way, which is why a build in a container needs no additional configuration.

> Note: For PyPI-indexes the same mechanism is not implemented yet.

### Custom pre-codeunit-build-scripts

Optional Python-scripts which are executed at the beginning of a codeunit-build, before the first codeunit is built (and before the `PrepareBuildCodeunits.py` of the repository). They are meant for machine-specific preparation-commands - for example logging in to a registry or providing credentials - and are located outside of any repository on purpose, so they are never committed.

Which script is executed depends on where the build runs:

| File | Executed by | Executed where |
|---|---|---|
| `TFCPS/CustomPreCodeUnitBuildScript.py` | `scbuildcodeunits` | on the host, at the beginning of the build |
| `TFCPS/CustomPreCodeUnitBuildScriptForContainer.py` | `scbuildcodeunitsc` (`scbuildcodeunits -c`) | on the host, before the build-container is started |
| `TFCPS/CustomPreCodeUnitBuildScriptInContainer.py` | `scbuildcodeunitsc` (`scbuildcodeunits -c`) and a build-pipeline | inside the build-container, at the beginning of the build |

Every script is optional: a file which does not exist is skipped without an error. The scripts are executed with the folder they are located in as working-directory, so a script can use files located next to it.

`CustomPreCodeUnitBuildScriptInContainer.py` is mounted read-only into the container (to `/Workspace/CustomScripts`) by the host-call which starts it. When the build runs in a container which gets the whole configuration-folder mounted instead - which is the recommended setup for a self-hosted build-runner, see [Build-runner-configuration](./BuildRunnerConfiguration.md) - the script is taken from there, so the same script also runs in a pipeline-build.

`CustomPreCodeUnitBuildScriptForContainer.py` runs before the values of the required environment-variables are resolved, so it can also create the files those values are read from.

Each script is called with the following arguments:

```cmd
python CustomPreCodeUnitBuildScript.py --repository <repository> --targetenvironmenttype <Development|QualityCheck|Productive> --verbosity <loglevel> [--additionalargumentsfile <file>] [--nocache]
```

`--repository` is the path of the repository which is built - inside the container this is the path the repository is mounted to, not the path on the host.

### Order of the preparation-steps

The two mechanisms described above (required environment-variables and custom scripts) are applied in a defined order, which matters when a script provides something the following steps depend on.

A build on the host (`scbuildcodeunits`):

1. The [required environment-variables](#required-environment-variables) are resolved and set in the environment of the build-process.
2. `~/.ScriptCollection/TFCPS/CustomPreCodeUnitBuildScript.py` is executed (it therefore already sees the environment-variables).
3. `<repository>/Other/Scripts/PrepareBuildCodeunits.py` is executed, if it exists.
4. The codeunits are built. Every sub-process started for a codeunit inherits the environment-variables.

A build in a container (`scbuildcodeunitsc`) - on the host:

1. `~/.ScriptCollection/TFCPS/CustomPreCodeUnitBuildScriptForContainer.py` is executed.
2. The values of the required environment-variables are resolved (so step 1 can still provide them).
3. The container is started: the repository is mounted, `CustomPreCodeUnitBuildScriptInContainer.py` is mounted read-only (if it exists) and the environment-variables are handed over to the container.

Inside the container `scbuildcodeunits` then runs the same steps as a build on the host, with two differences: the environment-variables are only verified (not resolved, see below) and `CustomPreCodeUnitBuildScriptInContainer.py` is executed instead of `CustomPreCodeUnitBuildScript.py`.

## Per-repository configuration

In addition to the machine-wide `~/.ScriptCollection`-folder, each repository has its own `<repository>/.ScriptCollection`-folder. The most relevant files there are:

- `<repository>/.ScriptCollection/OCIImages/ImageDefinition.csv`: Defines which OCI-images the repository uses, their upstream- (fallback-) registry and the default-tag. Columns: `ImageName;UpstreamRegistryAddress;DefaultTag`.

```csv
ImageName;UpstreamRegistryAddress;DefaultTag
Debian;docker.io/library/debian;13.4-slim
```

This file (per repository) defines the fallback-registry and tag, while `~/.ScriptCollection/GlobalCache/OCIImages/ImageRegistries.csv` (machine-wide) defines the custom registry to prefer.

### `<repository>/.betterleaks.toml`

Configures the secret-scan which runs as part of `scbuildcodeunits`. The scan has two parts:

- The repository-content is scanned with betterleaks.
- The OCI-image-artifacts (`<codeunit>/Other/Artifacts/BuildResult_OCIImage/*.tar`) are scanned separately, because betterleaks does not look into archives and because a built image can contain secrets which are not part of the repository at all: build-arguments recorded in the image-history, environment-variables and labels of the image, and files which are copied or generated during the image-build. An image is published to a registry, so a secret inside it is readable by everybody who is allowed to pull it.

The `[[allowlists]]`-entries of this file apply to both parts, so known false positives only have to be configured once.

### Required environment-variables

A repository declares which environment-variables its build needs in `<repository>/.ScriptCollection/ProductInformation.xml`. Only the names are declared there; the values are never part of the repository.

```xml
<cps:productinformation
    xmlns:cps="https://projects.aniondev.de/PublicProjects/Common/ProjectTemplates/-/tree/main/Conventions/RepositoryStructure/CommonProjectStructure"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <cps:producttitle>MyProduct</cps:producttitle>
    <cps:remoteaddress>https://example.com/MyProduct</cps:remoteaddress>
    <cps:requiredenvironmentvariables>
        <cps:requiredenvironmentvariable>MY_ACCESS_TOKEN</cps:requiredenvironmentvariable>
        <cps:requiredenvironmentvariable>MY_OTHER_VARIABLE</cps:requiredenvironmentvariable>
    </cps:requiredenvironmentvariables>
</cps:productinformation>
```

The `requiredenvironmentvariables`-element is **required**. A product whose build does not need any environment-variable declares it empty:

```xml
    <cps:requiredenvironmentvariables></cps:requiredenvironmentvariables>
```

This way it is always visible which environment-variables a product depends on; a missing element is a mistake and not the statement "no variables needed", and the build reports it as such.

The value of every declared variable is resolved from the machine-wide [`~/.ScriptCollection/TFCPS/EnvironmentVariables.csv`](#tfcpsenvironmentvariablescsv). This happens for every build:

- When the codeunits are built on the host (`scbuildcodeunits`), the variables are set in the environment of the build-process, so every sub-process started for a codeunit inherits them.
- When the codeunits are built in a container (`scbuildcodeunitsc`, `scbuildcodeunits -c`), the variables are additionally passed into the container, so they do not have to be specified on every call. Only their names are passed as arguments; the values are given to the docker-client through its environment, so a value never appears in a log or in the process-list.
- When a single codeunit is built directly (for example `<codeunit>/Other/Build/Build.py` or `task bb`), the variables are set as well, so such a build behaves like a build started with `scbuildcodeunits`.

If a declared variable has no entry in `~/.ScriptCollection/TFCPS/EnvironmentVariables.csv`, the build aborts with a corresponding error-message.

If a declared variable is not defined in that file, its value is taken from the environment of the build-process. That is how a build-pipeline provides a value from its own secret-store. The configuration-file has precedence, so a resolved value does not depend on what happens to be set in the environment of the caller. If a value can not be determined in either way, the build aborts with a message which names both possibilities.

Because the configuration-file is looked up in the configuration-folder, a build-container which gets that folder mounted resolves the values exactly like a build on a host does. See [Build-runner-configuration](./BuildRunnerConfiguration.md) for the setup of a self-hosted build-runner.
