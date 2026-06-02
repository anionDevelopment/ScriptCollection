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
│   ├── CustomPreCodeUnitBuildScript.py
│   └── CustomC#Dependencies.csv
└── GlobalCache/
    ├── Tools/                          # downloaded tools (see DownloadableTools.md)
    ├── OCIImages/
    │   └── ImageRegistries.csv
    ├── RegistryCredentials.csv
    ├── Pip/
    │   ├── MainIndex.txt
    │   └── ExtraIndexURLs/
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

### `GlobalCache/Pip`

Configures custom PyPI-index-URLs which are passed to `pip` (for example to use a private package-index).

- `GlobalCache/Pip/MainIndex.txt`: Contains a line starting with `IndexURL: ` followed by the main index-url (passed as `--index-url`).
- `GlobalCache/Pip/ExtraIndexURLs/`: A folder; each file inside it contains a line starting with `IndexURL: ` followed by an additional index-url (each passed as `--extra-index-url`).

```text
IndexURL: https://my-private-index.example.com/simple
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

### `TFCPS/CustomPreCodeUnitBuildScript.py`

A custom Python-script that is executed before the codeunits are built (by `scbuildcodeunits`). It is run from the `~/.ScriptCollection/TFCPS`-folder and receives the same build-arguments. Use it for environment-specific preparation that should run on this machine before every build.

### `TFCPS/CustomC#Dependencies.csv`

Adds custom NuGet-sources that are registered before C#-codeunits are built. It is a comma-separated CSV with the header `Name,Url,Username,Password` (`Username` and `Password` are optional).

```csv
Name,Url,Username,Password
MyPrivateFeed,https://my-nuget.example.com/v3/index.json,user,pa$$w0rD
```

> The same NuGet-sources can alternatively be provided via environment-variables of the form `Dependency_CSharp_<Name>_Name`, `Dependency_CSharp_<Name>_URL`, `Dependency_CSharp_<Name>_Username` and `Dependency_CSharp_<Name>_Password`.

## Per-repository configuration

In addition to the machine-wide `~/.ScriptCollection`-folder, each repository has its own `<repository>/.ScriptCollection`-folder. The most relevant file there is:

- `<repository>/.ScriptCollection/OCIImages/ImageDefinition.csv`: Defines which OCI-images the repository uses, their upstream- (fallback-) registry and the default-tag. Columns: `ImageName;UpstreamRegistryAddress;DefaultTag`.

```csv
ImageName;UpstreamRegistryAddress;DefaultTag
Debian;docker.io/library/debian;13.4-slim
```

This file (per repository) defines the fallback-registry and tag, while `~/.ScriptCollection/GlobalCache/OCIImages/ImageRegistries.csv` (machine-wide) defines the custom registry to prefer.
