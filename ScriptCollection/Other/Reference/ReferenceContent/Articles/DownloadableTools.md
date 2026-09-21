# Downloadable tools

## Overview

ScriptCollection uses several external tools (for example for SBOM-generation or diagram-rendering).
Instead of requiring them to be installed system-wide, ScriptCollection downloads them on demand and stores them in the global cache-folder `~/.ScriptCollection/GlobalCache/Tools`.

For each of these tools there are two kinds of functions on `TFCPS_Tools_General`:

- An `ensure_<tool>_is_available(...)`-function that makes sure the tool is present (downloading it if necessary) and returns the path to the tool so it can be **used**.
- A `download_<tool>(enforce_update=False)`-function that only **downloads** the tool into the global cache (all platforms), without using it.

The `ensure_*`-functions are called automatically during a build when the respective tool is needed, so usually you do not have to call anything manually.

## Available tools

| Tool | Download-function | Use-function | Source |
|------|-------------------|--------------|--------|
| CycloneDX-CLI | `download_cyclonedx` | `ensure_cyclonedxcli_is_available` | GitHub `CycloneDX/cyclonedx-cli` |
| JRE (Eclipse-Temurin) | `download_jre` | `ensure_jre_is_available` | GitHub `adoptium/temurin21-binaries` |
| MediaMTX | `download_mediamtx` | `ensure_mediamtx_is_available` | GitHub `bluenviron/mediamtx` |
| TruffleHog | `download_trufflehog` | `ensure_trufflehog_is_available` | GitHub `trufflesecurity/trufflehog` |
| OpenAPIGenerator | `download_openapigenerator` | `ensure_openapigenerator_is_available` | Maven-Central (`org.openapitools`) |
| AndroidAppBundleTool | `download_androidappbundletool` | `ensure_androidappbundletool_is_available` | GitHub `google/bundletool` |

All of these tools are stored in the global cache (`~/.ScriptCollection/GlobalCache/Tools`).
The CycloneDX-CLI and MediaMTX are downloaded for all supported platforms (linux/windows/macOS, x64/arm64 where available) so the warmed cache can be reused independent of the executing platform.
The JRE is the exception here: only the executing platform is warmed, because a JDK-archive is large (~200 MB) and the build-image is built per-platform. A specific Temurin-build is pinned (not just the major-version). It is used by tools which need a locally runnable JVM; the PlantUML-diagrams are **not** rendered with it (see [Rendering of PlantUML-diagrams](#rendering-of-plantuml-diagrams) below).

## Rendering of PlantUML-diagrams

PlantUML is deliberately **not** one of these tools: nothing of it is installed on the executing machine. The diagrams are always rendered inside a short-lived, disposable container which runs the image that the repository declares as `PlantUML` in `<repository>/.ScriptCollection/OCIImages/ImageDefinition.csv`:

```
ImageName;UpstreamRegistryAddress;DefaultTag
PlantUML;plantuml/plantuml;1.2026.8
```

PlantUML itself, the java-runtime, Graphviz (which PlantUML needs to lay out component- and class-diagrams) and the fonts are all part of that image, so the declared tag alone determines what a diagram looks like. That is what makes the generated SVG byte-identical on every machine - a developer on Windows and the build-container on Linux produce the same file, so a regenerated diagram never shows up as a spurious change. It was verified that this even holds across CPU-architectures (the same diagram rendered with the amd64- and with the arm64-variant of the image is byte-identical).

The reason this matters: PlantUML computes the whole SVG-geometry from the font-metrics of the JVM. Windows- and Linux-builds of a JDK use the same FreeType-based rasterizer and round identically, but a macOS-build uses Apple's CoreText and rounds the vertical metrics slightly differently, which shifts positions in the rendered SVG. Rendering with one pinned Linux-image everywhere avoids that.

When the declared tag is bumped, the committed diagram-SVGs have to be regenerated and re-committed once.

Because the rendering uses an image, nothing of it is part of the tools-cache which `scdownloadcachabletools` fills. The image is pulled through the regular image-manager instead: the machine-wide `~/.ScriptCollection/GlobalCache/OCIImages/ImageRegistries.csv` decides which registry is preferred for an image-name, and the `UpstreamRegistryAddress` of the repository's own `ImageDefinition.csv` is the fallback when no custom registry is defined for it. A machine which must not pull from Docker Hub therefore only needs an entry `PlantUML;<own-registry>/plantuml` there; see [ConfigurationFolder.md](./ConfigurationFolder.md).

Two details of the invocation:

- The font is pinned on the commandline (`-SdefaultFontName=...`) instead of in every single `.plantuml`-file, so a hand-written diagram is rendered with the same font as a generated one.
- The image runs as an own unprivileged user. On Linux and macOS the container is therefore started with the uid/gid of the user who runs the build, so the generated SVG belongs to that user.

When the build itself runs in a container whose docker-socket is forwarded to the daemon of the host (for example a build in the SCBuilder-image), the rendering-container is a *sibling*-container: a bind-mount of a path of the build-container would be resolved by the daemon of the host, where that path does not exist, and docker would silently mount an empty directory instead. The volumes of the own container are therefore shared with the rendering-container (`--volumes-from`), which makes the repository visible there under exactly the same path.

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
- **PlantUML**: This is used as an OCI-image (see [Rendering of PlantUML-diagrams](#rendering-of-plantuml-diagrams) above), not as a cached jar. An image is not pre-warmed by this command at all: which registry it is pulled from is decided by the image-manager (see below).
- **Syft**: This is used as an OCI-image (pulled via the image-manager / custom registry, see [Custom OCI-registries](./CustomOCIRegistries.md)), not as a cached binary in the tools-cache.

## Cleaning the cache

The counterpart to pre-downloading is `sccleantoolscache`, which empties the global cache-folder.
