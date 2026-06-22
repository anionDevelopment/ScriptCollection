# Downloadable tools

## Overview

ScriptCollection uses several external tools (for example for SBOM-generation or diagram-rendering).
Instead of requiring them to be installed system-wide, ScriptCollection downloads them on demand and stores them in the global cache-folder `~/.scriptcollection/GlobalCache/Tools`.

For each of these tools there are two kinds of functions on `TFCPS_Tools_General`:

- An `ensure_<tool>_is_available(...)`-function that makes sure the tool is present (downloading it if necessary) and returns the path to the tool so it can be **used**.
- A `download_<tool>(enforce_update=False)`-function that only **downloads** the tool into the global cache (all platforms), without using it.

The `ensure_*`-functions are called automatically during a build when the respective tool is needed, so usually you do not have to call anything manually.

## Available tools

| Tool | Download-function | Use-function | Source |
|------|-------------------|--------------|--------|
| CycloneDX-CLI | `download_cyclonedx` | `ensure_cyclonedxcli_is_available` | GitHub `CycloneDX/cyclonedx-cli` |
| PlantUML | `download_plantuml` | `ensure_plantuml_is_available` | GitHub `plantuml/plantuml` |
| JRE (Eclipse-Temurin) | `download_jre` | `ensure_jre_is_available` | GitHub `adoptium/temurin21-binaries` |
| MediaMTX | `download_mediamtx` | `ensure_mediamtx_is_available` | GitHub `bluenviron/mediamtx` |
| TruffleHog | `download_trufflehog` | `ensure_trufflehog_is_available` | GitHub `trufflesecurity/trufflehog` |
| OpenAPIGenerator | `download_openapigenerator` | `ensure_openapigenerator_is_available` | Maven-Central (`org.openapitools`) |
| AndroidAppBundleTool | `download_androidappbundletool` | `ensure_androidappbundletool_is_available` | GitHub `google/bundletool` |

All of these tools are stored in the global cache (`~/.scriptcollection/GlobalCache/Tools`).
The CycloneDX-CLI and MediaMTX are downloaded for all supported platforms (linux/windows/macOS, x64/arm64 where available) so the warmed cache can be reused independent of the executing platform.
The JRE is the exception here: only the executing platform is warmed, because a JDK-archive is large (~200 MB) and the build-image is built per-platform. A specific Temurin-build is pinned (not just the major-version) and used to render all PlantUML-diagrams instead of the host's `java` on the `PATH`. Together with the bundled DejaVu-font this makes the rendered diagram-SVGs byte-identical across machines (e.g. a Windows-client and the Debian-build-container), because PlantUML computes the SVG-geometry purely from the JDK's font-metrics, which differ slightly between JDK-builds. When the pinned build is bumped, the committed diagram-SVGs must be regenerated and re-committed once.

## Pre-downloading all tools (`scdownloadcachabletools`)

There is one CLI-command that downloads all cachable tools at once:

```bash
scdownloadcachabletools
```

It calls `TFCPS_Tools_General.download_all_cachable_tools`, which in turn calls every `download_<tool>`-function.

Options:

- `-v` / `--verbose`: Enables verbose (debug) output (logs each tool that is being downloaded).
- `-e` / `--enforceupdate`: Re-downloads the tools even if they are already present in the cache.

### Why this is useful

The main use-case is to call `scdownloadcachabletools` inside a build-image (for example in the `Dockerfile` of the CI build-environment).
Because the tools are then already present in the image:

- repeated pipeline-runs do not hit the rate-limits of the download-sources (for example the GitHub-API), and
- the pipeline runs faster, because nothing has to be downloaded at build-time.

Example (in a `Dockerfile` of the build-image, after ScriptCollection has been installed):

```dockerfile
RUN scdownloadcachabletools
```

## Tools that are not part of this command

Some tools are handled differently and are therefore not downloaded by `scdownloadcachabletools`:

- **FFMPEG** (`ensure_ffmpeg_is_available`): This is not stored in the global cache but downloaded directly into a specific codeunit's `Other/Resources/FFMPEG`-folder. It is therefore codeunit-specific and cannot be pre-warmed independent of a codeunit. (In a build-image, ffmpeg is usually installed as a system-package instead.)
- **Syft**: This is used as an OCI-image (pulled via the image-manager / custom registry, see [UsingCustomImageRegistry.md](./UsingCustomImageRegistry.md)), not as a cached binary in the tools-cache.

## Cleaning the cache

The counterpart to pre-downloading is `sccleantoolscache`, which empties the global cache-folder.
