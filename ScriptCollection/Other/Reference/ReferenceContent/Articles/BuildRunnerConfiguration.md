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

Create the folder once per runner-host, for example `/srv/ScriptCollectionConfiguration`. It is a copy of the parts of a developer's `~/.ScriptCollection` which a build needs:

```text
/srv/ScriptCollectionConfiguration/
├── TFCPS/
│   ├── EnvironmentVariables.csv
│   └── Secrets/
│       └── MyToken.txt
└── GlobalCache/
    └── OCIImages/
        └── ImageRegistries.csv
```

```csv
EnvVariableName;Kind;Value
Dependency_CSharp_MyPrivateFeed_URL;literal;https://example.com/api/v4/projects/1/packages/nuget/index.json
Dependency_CSharp_MyPrivateFeed_Username;literal;myuser
Dependency_CSharp_MyPrivateFeed_Password;file;Secrets/MyToken.txt
```

Use a **relative** path for a secret-file (it is resolved against `<configuration-folder>/TFCPS`). An absolute path or a `~`-path of the developer-machine does not exist inside the container.

> **Create `GlobalCache/OCIImages/ImageRegistries.csv` even if it is empty** (a file containing only the header-line `ImageName;RegistryAddress` is enough). The mount is read-only, but ScriptCollection creates that file - and the folders above it - when it does not exist yet. On a read-only mount that creation fails and the build aborts, so a folder which only contains `TFCPS` breaks every build on this runner. See [Custom OCI-registries](./CustomOCIRegistries.md) for what to put into that file.

Restrict the access-rights of the folder to the user which runs the runner (for example `chmod 600` for the files below `Secrets`).

> **The path on the left side is always a path on the runner-host**, in every setup below - never a path inside the runner-container. A self-hosted runner which itself runs as a container creates the job-container through the docker-socket it has mounted, so that mount-source is resolved by the docker-daemon on the host. The configuration-folder therefore does **not** have to be mounted into the runner-container itself; the runner only passes the path on. (Mounting it there as well does no harm and can help to verify the setup, for example with `docker compose exec <runner> ls /srv/ScriptCollectionConfiguration`.)

### GitLab (official runner-image, docker-executor)

The runner itself only needs its own configuration and the docker-socket:

```yaml
services:
  gitlab-runner:
    image: gitlab/gitlab-runner:latest
    container_name: gitlab-runner
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - /srv/gitlab-runner/config:/etc/gitlab-runner
```

The mount into the **job**-containers is configured once in the `config.toml` of that runner (here: `/srv/gitlab-runner/config/config.toml`) and then applies to every project this runner builds - no repository has to be changed:

```toml
[[runners]]
  [runners.docker]
    volumes = ["/var/run/docker.sock:/var/run/docker.sock", "/srv/ScriptCollectionConfiguration:/root/.ScriptCollection:ro"]
```

Afterwards restart the runner (`docker compose restart gitlab-runner`) so the changed configuration takes effect.

A build on a build-server should additionally state that it is one, so that a step which only makes sense on a developer-machine is skipped instead of failing here (see [Telling a build that it runs on a build-server](#telling-a-build-that-it-runs-on-a-build-server)):

```toml
[[runners]]
  environment = ["IS_RUNNING_IN_SERVER_PIPELINE=true"]
```

### GitHub (SCGitHubRunner)

`SCGitHubRunner` (a codeunit of the `SCBuilder`-repository) adds this mount to every job-container it starts, configured once per runner with `SCRIPTCOLLECTION_CONFIGURATION_FOLDER` - so no repository-workflow has to be changed:

```yaml
services:
  myrunner:
    image: aniondev/scgithubrunner:latest
    container_name: myrunner
    restart: unless-stopped
    environment:
      ORG_NAME: myorganization
      ACCESS_TOKEN: <github-personal-access-token>
      RUNNER_NAME: myrunner
      LABELS: self-hosted,scriptcollection
      RUNNER_HOME: /Workspace/Other/Runner/MyRunner
      SCRIPTCOLLECTION_CONFIGURATION_FOLDER: /srv/ScriptCollectionConfiguration
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      # host-identical and unique per runner (see SCGitHubRunner's own documentation):
      - /Workspace/Other/Runner/MyRunner:/Workspace/Other/Runner/MyRunner
```

This requires an `SCGitHubRunner`-image which contains the container-hook (see the "Container-hooks" section of its usage-documentation); after updating the image, `docker compose pull && docker compose up -d` on the runner-host. That same hook also sets `IS_RUNNING_IN_SERVER_PIPELINE` in every job-container it starts (see below), so nothing has to be configured for that here.

### GitHub (any other runner-image)

With a runner-image which can not be extended that way, the job-container is defined by the workflow, so the mount is added to `.github/workflows/buildpipeline.yml` of every repository which needs it:

```yaml
jobs:
  build-pipeline:
    runs-on: [self-hosted, scriptcollection]
    container:
      image: aniondev/scbuilder:v1.2.9
      volumes:
        - /var/run/docker.sock:/var/run/docker.sock
        - /srv/ScriptCollectionConfiguration:/root/.ScriptCollection:ro
```

### Target-path of the mount

`/root/.ScriptCollection` is the configuration-folder of the user the job-container runs as. The SCBuilder-image runs as `root`; for an image which runs as another user the target-path is the `.ScriptCollection`-folder in the home-directory of that user.

The mount is needed for a repository which declares required environment-variables, and it is also what makes a custom OCI-registry (and its credentials) available to every build on this runner - see [Custom OCI-registries](./CustomOCIRegistries.md).

## Telling a build that it runs on a build-server

A build-server deliberately provides less than a developer-machine: it has the configuration-folder, but not the developer's personal tooling and credential-files. A preparation-step which uses those has to be skipped there instead of failing - and a build can not derive that situation on its own, because a build which was started with `scbuildcodeunits -c` on a developer-machine also runs in a container and is otherwise indistinguishable from a job-container of a runner. It is therefore stated explicitly, with the environment-variable `IS_RUNNING_IN_SERVER_PIPELINE`:

```yaml
IS_RUNNING_IN_SERVER_PIPELINE: "true"
```

It is set in three places, which do not conflict because they all set the same value:

- in the pipeline-definition of the repository (`env:` of the workflow respectively `variables:` of `.gitlab-ci.yml`) - this is where the generated pipeline-files put it,
- by the GitLab-runner, for every job it starts (`environment` in its `config.toml`, see above),
- by `SCGitHubRunner`, for every job-container it starts (its container-hook sets it unconditionally).

Setting it on the runner as well is what makes a repository whose pipeline-file is older than this convention work anyway: the preparation which needs it runs before the step which would update that pipeline-file, so a repository which only relies on its own pipeline-file can not repair itself.

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
