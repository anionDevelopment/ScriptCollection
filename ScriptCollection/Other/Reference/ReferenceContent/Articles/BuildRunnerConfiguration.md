# Build-runner-configuration

## Overview

A build which runs in a build-pipeline needs the same machine-specific information as a build on a developer-machine: the values of the [required environment-variables](./ConfigurationFolder.md#required-environment-variables) of the product, for example the credentials of a private package-source.

A repository declares only the **names** of the environment-variables it needs (in `<repository>/.ScriptCollection/ProductInformation.xml`); the **values** are never part of the repository. In a build-pipeline the values therefore have to come from the build-infrastructure. ScriptCollection resolves a value from one of two sources:

1. From `~/.ScriptCollection/TFCPS/EnvironmentVariables.csv`, if the variable is defined there.
2. From the environment of the build-process otherwise.

The configuration-file has precedence, so a resolved value does not depend on what happens to be set in the environment of the caller. If a value can not be determined in either way, the build aborts with a message which names both possibilities.

Both sources work everywhere - on a developer-machine, inside a build-container and in a build-pipeline. The recommended setup for self-hosted runners is the first one, because it uses exactly the same file (and the same format) as a developer-machine.

## Recommended setup: mount the configuration-folder into the job-container

The build of a pipeline runs in a container (usually the SCBuilder-image). Mounting a folder of the runner-host as the configuration-folder of that container makes ScriptCollection resolve the values there exactly like it does on a host.

> Note: The environment-variables of the **runner-process** are not inherited by a **job-container**, so configuring them in the runner-image or in the docker-compose-file of the runner does not make them available to the build. The mount (or the secret-store of the forge, see below) is what reaches the job-container.

### Folder on the runner-host

Create the folder once per runner-host, for example `/srv/ScriptCollectionConfiguration`:

```text
/srv/ScriptCollectionConfiguration/
└── TFCPS/
    ├── EnvironmentVariables.csv
    └── Secrets/
        └── MyToken.txt
```

```csv
EnvVariableName;Kind;Value
Dependency_CSharp_MyPrivateFeed_URL;literal;https://example.com/api/v4/projects/1/packages/nuget/index.json
Dependency_CSharp_MyPrivateFeed_Username;literal;myuser
Dependency_CSharp_MyPrivateFeed_Password;file;Secrets/MyToken.txt
```

Use a **relative** path for a secret-file (it is resolved against `<configuration-folder>/TFCPS`). An absolute path or a `~`-path of the developer-machine does not exist inside the container.

Restrict the access-rights of the folder to the user which runs the runner (for example `chmod 600` for the files below `Secrets`).

### GitLab

The official GitLab-runner-image is used with the docker-executor, so the mount is configured once in the `config.toml` of the runner and applies to every project which is built by that runner - no repository has to be changed:

```toml
[[runners]]
  [runners.docker]
    volumes = ["/var/run/docker.sock:/var/run/docker.sock", "/srv/ScriptCollectionConfiguration:/root/.ScriptCollection:ro"]
```

### GitHub

The workflow defines the job-container, so the mount is added to `.github/workflows/buildpipeline.yml` of the repository:

```yaml
jobs:
  build-pipeline:
    runs-on: [self-hosted, scriptcollection]
    container:
      image: aniondev/scbuilder:v1.2.5
      volumes:
        - /var/run/docker.sock:/var/run/docker.sock
        - /srv/ScriptCollectionConfiguration:/root/.ScriptCollection:ro
```

`/root/.ScriptCollection` is the configuration-folder of the user the job-container runs as. The SCBuilder-image runs as `root`; for an image which runs as another user the target-path is the `.ScriptCollection`-folder in the home-directory of that user.

The mount is only needed for repositories which actually declare required environment-variables.

## Alternative: the secret-store of the forge

If a value has to be managed by the forge (for example because it differs per repository or is rotated there), it is provided as an environment-variable of the build-job instead. ScriptCollection then takes it from the environment.

- **GitLab**: define a CI/CD-variable (masked and protected) on group- or project-level. It is available in the job automatically; no repository-change is needed. Additionally the variable can be passed per run when the pipeline is triggered via the API.
- **GitHub**: define an organization- or repository-secret and map it in the workflow:

```yaml
    env:
      Dependency_CSharp_MyPrivateFeed_Password: ${{ secrets.MY_PRIVATE_FEED_PASSWORD }}
```

A `workflow_dispatch`-input is **not** suitable for a secret: inputs have to be declared in the workflow and their values are visible in the run-overview.

## Security

- Everything which is mounted into a job-container (or provided as a job-environment-variable) is readable by every job which runs on that runner. On a runner which also builds repositories that accept contributions from outside, use a separate runner-instance with an own label for the repositories which need the credentials.
- Mount the configuration-folder read-only (`:ro`): a build never has to change it.
- Do not place secret-files inside the workspace of the repository: they would end up in the repository-scan, in the artifacts or in a built image.
- Never pass a secret as a build-argument of an image-build: build-arguments are recorded in the image-history and are readable by everybody who can pull the image (the [secret-scan of the built images](../Hints.md#secret-scan-of-oci-images) reports this).
