# Workflow 2: Docker Full Lifecycle — Complete Documentation

> **File:** `.github/workflows/docker-full-lifecycle.yml`
>
> **Purpose:** A production-grade Docker image lifecycle workflow covering multi-architecture
> builds, vulnerability scanning, SBOM generation, Cosign keyless signing, SLSA provenance,
> image verification, GitHub Release creation, and storage cleanup.
>
> **Audience:** Developers and DevOps engineers learning GitHub Actions and Docker security

## Table of Contents

1. [Overview](#1-overview)
2. [Trigger Configuration (`on:`)](#2-trigger-configuration-on)
3. [Permissions](#3-permissions)
4. [Environment Variables](#4-environment-variables)
5. [Job 1: docker-setup](#5-job-1-docker-setup)
6. [Job 2: docker-lint](#6-job-2-docker-lint)
7. [Job 3: metadata](#7-job-3-metadata)
8. [Job 4: build-push](#8-job-4-build-push)
9. [Job 5: image-scan](#9-job-5-image-scan)
10. [Job 6: sbom-attest](#10-job-6-sbom-attest)
11. [Job 7: verify-image](#11-job-7-verify-image)
12. [Job 8: release](#12-job-8-release)
13. [Job 9: cleanup](#13-job-9-cleanup)
14. [Docker Concepts Reference](#14-docker-concepts-reference)
15. [GitHub Actions Concepts Reference](#15-github-actions-concepts-reference)

---

## 1. Overview

### What This Workflow Does

This workflow implements a **Docker container image lifecycle pipeline** — every image goes
through build, scan, sign, verify, and release before being published. It demonstrates:

1. **Multi-architecture setup** — QEMU emulation + BuildKit for amd64/arm64 builds
2. **Dockerfile linting** — Hadolint best-practice validation with SARIF upload
3. **Metadata generation** — OCI-compliant tags and labels from Git context
4. **Multi-platform build + push** — Parallel amd64/arm64 with layer caching
5. **Vulnerability scanning** — Trivy deep CVE scan + Docker Scout policy evaluation
6. **SBOM + signing** — SPDX bill of materials + Cosign keyless signing
7. **Image verification** — Digest-pinned pull, signature verify, manifest inspection
8. **Release creation** — GitHub Release with all artifacts attached
9. **Storage cleanup** — Untagged image version pruning

### Architecture Diagram

```
on: workflow_dispatch or release:published
         │
         ▼
  ┌──────────────┐
  │ docker-setup  │  ←── QEMU + Buildx (docker-container driver)
  └──────┬───────┘
         │
         ├──────────────────────────┐
         ▼                          ▼
  ┌──────────────┐         ┌────────────────┐
  │  docker-lint  │         │   metadata     │  ←── parallel
  │ (Hadolint)    │         │ (tags + labels)│
  └──────┬───────┘         └───────┬────────┘
         │                          │
         └──────────┬───────────────┘
                    ▼
          ┌──────────────────┐
          │   build-push      │  ←── multi-arch + provenance + SBOM
          └────────┬─────────┘
                   │
         ┌─────────┴──────────┐
         ▼                    ▼
  ┌──────────────┐   ┌──────────────┐
  │  image-scan   │   │ sbom-attest  │  ←── parallel
  │ (Trivy+Scout) │   │ (SBOM+Cosign)│
  └──────┬───────┘   └──────┬───────┘
         │                    │
         └────────┬──────────┘
                  ▼
         ┌──────────────────┐
         │  verify-image     │  ←── pull + verify + inspect
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │     release       │  ←── GitHub Release (optional)
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │     cleanup       │  ←── prune untagged (main only)
         └──────────────────┘
```

### Key Design Principles

1. **Digest immutability over tags:** Every job that consumes the image uses the SHA256 digest
   (`@sha256:...`), not a tag. Tags are mutable and can be overwritten; digests are
   content-addressable and unique to the image content.

2. **Defense in depth:** Multiple scanning tools (Trivy + Docker Scout) for broader CVE coverage.
   Multiple signing mechanisms (Cosign + SLSA attestation + GitHub attestation) for
   redundant verification.

3. **Shift left, verify right:** Dockerfile linting catches issues before the build.
   Post-build verification catches registry tampering after the push.

4. **Job DAG for parallel efficiency:** Independent jobs (docker-lint + metadata, image-scan +
   sbom-attest) run in parallel to minimize total wall-clock time.

5. **Emergency bypass:** The `skip-scan` input allows bypassing the security scan for
   emergency hotfixes, while maintaining all other pipeline steps.

---

## 2. Trigger Configuration (`on:`)

### YAML Block

```yaml
on:
  release:
    types: [published]
  workflow_dispatch:
    inputs:
      image-name:
        description: 'Container image name (default: ghcr.io/${{ github.repository }})'
        required: false
        type: string
      platforms:
        description: 'Target platforms (comma-separated, e.g. linux/amd64,linux/arm64)'
        required: false
        default: 'linux/amd64,linux/arm64'
        type: string
      skip-scan:
        description: 'Skip vulnerability scan (emergency use only)'
        required: false
        default: false
        type: boolean
```

### Line-by-Line Explanation

**`on:`** — The top-level key that defines which events trigger the workflow. GitHub Actions
supports many event types including `push`, `pull_request`, `release`, `schedule`, `workflow_dispatch`,
`workflow_call`, `repository_dispatch`, `issue_comment`, `registry_package`, and more.

**`release:`** — Trigger when a GitHub Release event occurs. This is useful for publishing
images that correspond to official releases of the software.

**`types: [published]`** — Sub-filter for the release event. Only trigger when the release
is published (not when it's created as a draft, edited, or deleted). Other release types
include: `created`, `edited`, `deleted`, `prereleased`, `unpublished`.

**`workflow_dispatch:`** — Allows manual triggering of the workflow from the GitHub UI,
REST API, or CLI (`gh workflow run`). This is essential for testing the pipeline without
creating a release.

**`inputs:`** — Defines the input parameters for `workflow_dispatch`. These appear as form
fields in the GitHub UI "Run workflow" dialog.

**`image-name:`** — An optional string input for overriding the container image name.
When not provided, the workflow defaults to `ghcr.io/${{ github.repository }}` which
expands to `ghcr.io/owner/repo-name`.

**`description:`** — The human-readable label shown in the GitHub UI form. Always provide
clear descriptions so team members know what each input does.

**`required: false`** — Whether the user must provide a value. When false, the input
defaults to empty or the specified `default` value.

**`type: string`** — The data type for the input. Supported types: `string`, `number`,
`boolean`, `choice`, `environment`.

**`platforms:`** — A string input for specifying target build platforms. The default
`linux/amd64,linux/arm64` covers the two most common server architectures. AWS Graviton
and Apple Silicon use arm64; traditional servers use amd64.

**`default: 'linux/amd64,linux/arm64'`** — The default value used when the user doesn't
provide one. For multi-arch builds, you'd add platforms like `linux/arm/v7` (Raspberry Pi),
`linux/s390x` (IBM mainframe), or `linux/ppc64le` (PowerPC).

**`skip-scan:`** — A boolean input for emergency bypass of vulnerability scanning. Setting
this to `true` skips the `image-scan` job. This is a deliberate risk-acceptance mechanism
for security hotfixes where the fix addresses a vulnerability that the scan would detect.

**`type: boolean`** — Renders as a checkbox in the GitHub UI. Valid values: `true` or `false`.

### Key Concepts

**Workflow dispatch with typed inputs** is one of the most powerful features of GitHub Actions
for operations workflows. The input types map to native HTML form elements:
- `string` → text input field
- `choice` → dropdown select (requires `options:` array)
- `boolean` → checkbox
- `number` → number input with validation

Unlike `pull_request` or `push` triggers that run automatically, `workflow_dispatch` requires
manual initiation. It's ideal for:
- Deployment workflows
- Release publishing pipelines
- Maintenance tasks (cleanup, migration)
- Testing/debugging workflows

The `release` event has a special relationship with tags. When a release is published:
1. GitHub creates a Git tag matching the release tag if one doesn't exist
2. The `github.ref` variable is set to the tag (e.g., `refs/tags/v1.2.3`)
3. The `github.event.release` object contains all release metadata

This is why the `release` job in our workflow checks `github.event_name == 'release'` —
it determines whether to create a new release (workflow_dispatch) or attach to an existing
one (release event).

---

## 3. Permissions

### YAML Block

```yaml
permissions:
  contents: write
  packages: write
  id-token: write
  attestations: write
  security-events: write
```

### Line-by-Line Explanation

**`permissions:`** — The top-level key for setting GITHUB_TOKEN permissions. By default,
GitHub Actions grants a scoped-down token with only `contents: read`. You must explicitly
request additional permissions.

**`contents: write`** — Required for:
- Pushing commits/tags (if applicable)
- Creating releases (`softprops/action-gh-release`)
- Uploading release assets
- Reading/writing repository contents

Without `contents: write`, the `release` job will fail when trying to create a GitHub Release.

**`packages: write`** — Required for:
- Pushing container images to GHCR (`docker/build-push-action`)
- Deleting package versions (`actions/delete-package-versions`)
- Any GitHub Packages API write operations

Without `packages: write`, the `build-push` job will get a 403 error when pushing to GHCR.

**`id-token: write`** — Required for:
- OIDC (OpenID Connect) token generation
- Cosign keyless signing (exchanges OIDC token with Fulcio)
- `actions/attest-build-provenance` (SLSA attestation)
- `slsa-framework/slsa-github-generator`

The OIDC token is requested from GitHub's OIDC provider at `https://token.actions.githubusercontent.com`.
Cosign uses this token to prove the workflow's identity to Fulcio (the certificate authority).

Without `id-token: write`, Cosign signing and attestation steps will fail because the
OIDC token won't be available.

**`attestations: write`** — Required for:
- `actions/attest-build-provenance@v2` to store attestations in the registry
- Creating cryptographically signed attestation objects

This is a relatively new permission (added with the attestation actions). It controls
write access to the attestations API endpoint.

Without `attestations: write`, the build provenance attestation step will fail.

**`security-events: write`** — Required for:
- Uploading SARIF files to GitHub Security tab
- Creating code scanning alerts
- `github/codeql-action/upload-sarif`

The SARIF format (Static Analysis Results Interchange Format) is an OASIS standard for
exchanging static analysis results. GitHub ingests SARIF files and displays them as
Code Scanning alerts.

Without `security-events: write`, SARIF upload steps will fail with a 403 error.

### Key Concepts

**GITHUB_TOKEN** is an automatically generated token scoped to the workflow run. It is:
- Created fresh for each workflow run
- Valid only for the duration of the run
- Automatically expires at the end of the run
- Exposed as `secrets.GITHUB_TOKEN`
- Scoped to the repository that contains the workflow

The principle of least privilege applies to CI/CD tokens too. Never set `permissions: write-all`.
Instead, explicitly list only the permissions needed.

**OIDC (OpenID Connect)** is an authentication protocol that allows one system to verify
the identity of another. In GitHub Actions, OIDC allows the workflow to obtain a token
that proves:
- Which repository it's running in
- Which workflow file initiated it
- Which branch/tag triggered it
- Which run ID and run number identify it

This OIDC token is the foundation of keyless signing. Instead of storing a private key
(which could be leaked), the workflow uses its ephemeral identity to prove it's authorized
to sign the artifact.

---

## 4. Environment Variables

### YAML Block

```yaml
env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}
  TRIVY_SEVERITY: CRITICAL,HIGH
```

### Line-by-Line Explanation

**`env:`** — Defines environment variables at the workflow level. These are available
to all jobs and steps in the workflow. Job-level and step-level `env:` blocks can
override these values for narrower scopes.

**`REGISTRY: ghcr.io`** — The container registry hostname. `ghcr.io` is GitHub Container
Registry. Alternative values:
- `docker.io` — Docker Hub (requires `DOCKER_USERNAME` and `DOCKER_PASSWORD` secrets)
- `quay.io` — Red Hat Quay
- `<account>.dkr.ecr.<region>.amazonaws.com` — AWS ECR
- `<name>.azurecr.io` — Azure ACR

Using an `env` variable makes it easy to change registries without editing multiple places
in the workflow.

**`IMAGE_NAME: ${{ github.repository }}`** — The image name, defaulting to the GitHub
repository name (`owner/repo`). In GHCR, the image path becomes `ghcr.io/owner/repo`.
The `${{ github.repository }}` variable is a built-in GitHub context variable.

**`TRIVY_SEVERITY: CRITICAL,HIGH`** — The severity threshold for Trivy vulnerability
scanning. Only vulnerabilities at these levels will cause the scan to fail. This is a
deliberate choice — MEDIUM and LOW findings rarely warrant blocking a build.

### Key Concepts

**GitHub Context (`github.*`):** GitHub Actions provides a rich context object accessible
via `${{ github.* }}`. Key variables:
- `github.repository` — Current repository (format: `owner/repo`)
- `github.ref` — Branch or tag ref (format: `refs/heads/main` or `refs/tags/v1.0.0`)
- `github.sha` — Commit SHA that triggered the workflow
- `github.actor` — User who triggered the workflow
- `github.run_id` — Unique run number
- `github.run_number` — Run number (increments per workflow)
- `github.workflow` — Workflow name
- `github.event_name` — Event that triggered the workflow
- `github.event` — Full event payload object
- `github.token` — The GITHUB_TOKEN itself

**Expression syntax (`${{ }}`):** Anything inside `${{ }}` is evaluated as an expression.
You cannot use arbitrary shell commands — only GitHub expression syntax including:
- Ternary: `${{ condition && 'value1' || 'value2' }}`
- Logical operators: `==`, `!=`, `&&`, `||`, `!`
- String methods: `startsWith`, `endsWith`, `contains`, `format`
- Object methods: `join`, `fromJSON`, `toJSON`
- Hash functions: `hashFiles`

Environment variables set in `env:` blocks are accessible in Shell steps as standard
environment variables (`$REGISTRY`) and in expressions as `${{ env.REGISTRY }}`.

---

## 5. Job 1: docker-setup

### YAML Block

```yaml
docker-setup:
  runs-on: ubuntu-latest
  outputs:
    builder-name: ${{ steps.buildx.outputs.name }}
  steps:
    - uses: actions/checkout@v4

    - name: Set up QEMU for multi-architecture emulation
      uses: docker/setup-qemu-action@v3
      with:
        platforms: arm64,arm

    - name: Set up Docker Buildx
      id: buildx
      uses: docker/setup-buildx-action@v3
      with:
        driver: docker-container
        driver-opts: |
          image=moby/buildkit:latest
        buildkitd-flags: --debug

    - name: Inspect builder
      run: |
        echo "Builder name: ${{ steps.buildx.outputs.name }}"
        echo "Driver: docker-container"
        echo "Supported platforms:"
        docker buildx inspect --bootstrap | grep -E "Platforms:|linux/"
```

### Line-by-Line Explanation

**`docker-setup:`** — Job ID. Must be unique within the workflow. Other jobs reference
this as `needs: docker-setup` or `${{ needs.docker-setup.outputs.* }}`.

**`runs-on: ubuntu-latest`** — Specifies the runner environment. `ubuntu-latest` is the
default Linux runner with Docker pre-installed. Other options include `windows-latest`,
`macos-latest`, `ubuntu-24.04`, `ubuntu-22.04`, `self-hosted`, or custom runner labels.

**`outputs:`** — Defines the job's output values that downstream jobs can consume.
Outputs are key-value pairs set by individual steps writing to `$GITHUB_OUTPUT`.

**`builder-name: ${{ steps.buildx.outputs.name }}`** — An output named `builder-name`
that captures the Buildx builder instance name. The value comes from the step with
`id: buildx`, specifically from the step's `outputs.name`.

**`steps:`** — An ordered list of steps within the job. Each step can run a command
(`run:`) or use a pre-built action (`uses:`).

**`- uses: actions/checkout@v4`** — The standard checkout action. Required because:
- The runner starts with a clean workspace
- We need the repository source code for other steps
- Some steps (like metadata) need Git history for tag/branch detection
- `hashFiles()` relies on files in the working directory

Key inputs for `actions/checkout@v4`:
- `fetch-depth: 0` — Fetch all history (needed for semver tags)
- `fetch-tags: true` — Fetch tags with history
- `persist-credentials: true` — Save token for later Git operations
- `path: ./some-dir` — Checkout to a subdirectory
- `ref: ${{ github.ref }}` — Checkout a specific ref

**`- name: Set up QEMU...`** — A human-readable step name. Displayed in the GitHub
UI workflow visualization.

**`uses: docker/setup-qemu-action@v3`** — A community action maintained by Docker.
It installs QEMU (Quick EMUlator) static binaries and registers them with the Linux
kernel's binfmt_misc subsystem.

**`with:`** — Passes inputs to the action.

**`platforms: arm64,arm`** — Specifies which architecture emulators to install. Each
platform requires a different QEMU static binary. Common values:
- `arm64` — 64-bit ARM (AArch64), used by AWS Graviton and Apple Silicon
- `arm` — 32-bit ARM, used by Raspberry Pi and older mobile devices
- `s390x` — IBM mainframe
- `ppc64le` — PowerPC little-endian
- `riscv64` — RISC-V 64-bit (open standard ISA)

Without QEMU, the Docker build on an amd64 runner can only produce amd64 images.
QEMU translates ARM instructions to x86 at runtime, enabling cross-architecture builds.

**`- name: Set up Docker Buildx`** — Initializes Docker Buildx which is Docker's
extended build system built on BuildKit technology.

**`id: buildx`** — Assigns an identifier to this step. The ID is used by other steps
to reference this step's outputs via `${{ steps.buildx.outputs.* }}`.

**`uses: docker/setup-buildx-action@v3`** — The official Docker action for configuring
Buildx. It handles:
- Creating/selecting a builder instance
- Installing BuildKit if needed
- Configuring the builder driver
- Connecting to remote builders

**`driver: docker-container`** — Specifies the Buildx driver. This is the critical
choice for multi-arch builds:

| Driver | Description | Multi-arch | Cache exports | Use case |
|---|---|---|---|---|
| `docker` | Built-in Docker BuildKit (embedded) | No | Limited | Simple local builds |
| `docker-container` | External BuildKit container | Yes | Full | CI/CD multi-arch |
| `kubernetes` | BuildKit pods in K8s cluster | Yes | Full | Enterprise CI |
| `remote` | Connect to remote BuildKit | Yes | Full | Shared build farm |

The `docker-container` driver launches a detached BuildKit container (`moby/buildkit`)
that handles the actual build. This is required because:
1. The embedded `docker` driver only builds for the host architecture
2. `docker-container` supports all cache export types
3. It handles concurrent builds better
4. It supports build attestations (provenance, SBOM)

**`driver-opts:`** — Additional options passed to the Buildx driver.

**`image=moby/buildkit:latest`** — Specifies which BuildKit image to use. The
`:latest` tag is convenient but not immutable. For production, pin to a specific
digest: `image=moby/buildkit@sha256:abcdef...`.

**`buildkitd-flags: --debug`** — Flags passed to the BuildKit daemon. `--debug`
enables verbose logging useful for troubleshooting build failures. For production,
consider using `--allow-insecure-entitlement network.host` if needed.

**`- name: Inspect builder`** — A diagnostic step that shows the builder configuration
in CI logs.

**`docker buildx inspect --bootstrap`** — The `--bootstrap` flag ensures the builder
is running (pulls the BuildKit image if needed). This command outputs:
```
Name:   builder-abc123
Driver: docker-container
Nodes:
  Name:      builder-abc1230
  Endpoint:  unix:///var/run/docker.sock
  Status:    running
  Platforms: linux/amd64, linux/arm64, linux/arm/v7, linux/arm/v8, ...
```

**`| grep -E "Platforms:|linux/"`** — Filters the output to show only the relevant
platform lines. This makes the CI log more readable by showing just the architecture
information.

### docker/setup-qemu-action@v3 — Full Capability Reference

Key inputs:
| Input | Default | Description |
|---|---|---|
| `platforms` | `all` | Comma-separated list of platforms to install |
| `image` | `tonistiigi/binfmt:latest` | QEMU binfmt image |
| `install` | `true` | Whether to register binfmt_misc handlers |

What this action does internally:
1. Runs a privileged container with `tonistiigi/binfmt` image
2. The container installs QEMU static binaries to `/proc/sys/fs/binfmt_misc/`
3. Registers QEMU interpreters for each requested platform
4. After this step, `docker run --platform linux/arm64 alpine uname -m` returns `aarch64`

### docker/setup-buildx-action@v3 — Full Capability Reference

Key inputs:
| Input | Default | Description |
|---|---|---|
| `driver` | `docker` | Builder driver (docker, docker-container, kubernetes, remote) |
| `driver-opts` | — | Driver-specific options (image, network, env) |
| `buildkitd-flags` | — | Flags for BuildKit daemon |
| `buildkitd-config` | — | BuildKit daemon config TOML |
| `endpoint` | — | Remote builder endpoint |
| `install` | `false` | Set builder as default for `docker build` |

Key outputs:
| Output | Description |
|---|---|
| `name` | Builder instance name |
| `platforms` | Comma-separated supported platforms |

### Why This Specific Approach

QEMU emulation is chosen over cross-compilation for several reasons:
1. **Transparency:** The Dockerfile builds the same way for every platform — no platform-specific
   branches or conditionals
2. **Compatibility:** Some packages don't cross-compile cleanly (native addons, C extensions)
3. **Simplicity:** One Dockerfile, one build command, multiple architectures
4. **Verification:** The same build process runs under emulation as on native hardware

The tradeoff is build speed — QEMU emulation is approximately 2-5x slower than native
execution for arm64 builds on amd64 runners. For projects with many native extensions,
consider using native arm64 runners with GitHub's larger hosted runners or self-hosted
options.

---

## 6. Job 2: docker-lint

### YAML Block

```yaml
docker-lint:
  needs: docker-setup
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Lint Dockerfile with Hadolint
      uses: hadolint/hadolint-action@v3
      with:
        dockerfile: Dockerfile
        failure-threshold: warning
        format: sarif
        output-file: hadolint-results.sarif

    - name: Upload SARIF to GitHub Security
      uses: github/codeql-action/upload-sarif@v3
      with:
        sarif_file: hadolint-results.sarif
        category: hadolint
```

### Line-by-Line Explanation

**`needs: docker-setup`** — Declares a dependency on the `docker-setup` job. This job
will not start until `docker-setup` completes successfully. While this job doesn't
directly use any Buildx/QEMU features, the dependency ensures proper ordering in the
DAG visualization.

**`uses: hadolint/hadolint-action@v3`** — A community action wrapping the Hadolint
Dockerfile linter. Hadolint is a static analysis tool that checks Dockerfiles against
best practices.

**`dockerfile: Dockerfile`** — Path to the Dockerfile to lint. Relative to the
repository root. The action reads this file and applies 100+ lint rules.

**`failure-threshold: warning`** — Determines which severity level causes the action
to fail. Options:
- `error` — Only actual errors fail the build
- `warning` — Warnings and errors fail the build (stricter)
- `info` — Info-level findings also fail
- `style` — Style suggestions also fail
- `none` — Never fail based on lint results

Using `warning` is a good balance — it catches real issues without being overly pedantic.

**`format: sarif`** — Output format for lint results. SARIF (Static Analysis Results
Interchange Format) is an OASIS standard JSON format. Other formats:
- `tty` — Terminal-colored output (default)
- `json` — Machine-readable JSON
- `checkstyle` — Checkstyle XML format
- `gitlab_codeclimate` — GitLab format
- `codeclimate` — Code Climate format

**`output-file: hadolint-results.sarif`** — Where to write the output. This file is
then uploaded to GitHub Security scanning.

**`uses: github/codeql-action/upload-sarif@v3`** — Uploads the SARIF file to GitHub
so results appear in the Security tab. Despite being in the CodeQL action package,
it handles any SARIF file, not just CodeQL results.

**`sarif_file: hadolint-results.sarif`** — Path to the SARIF file to upload.

**`category: hadolint`** — A categorization tag that distinguishes these results from
other scanning tools (CodeQL, Trivy, etc.) in the Security tab.

### Important Hadolint Rules Explained

**DL3006 — Always tag version explicitly:** Never use `FROM ubuntu` (implicit `:latest`).
Always use `FROM ubuntu:22.04` or `FROM node:20-bookworm-slim`. The `:latest` tag is
mutable and can change unexpectedly, breaking your build.

**DL3008 — Pin package versions in apt-get install:** Use `apt-get install curl=7.68.0-1`
instead of `apt-get install curl`. Without version pinning, builds are non-reproducible.

**DL3009 — Delete apt-get lists:** After `apt-get update`, always run `rm -rf /var/lib/apt/lists/*`
in the same RUN layer to keep images small.

**DL3018 — Pin package versions in apk add:** Alpine's `apk` should use pinned versions
like `apk add curl=7.79.1-r0`.

**DL3020 — Use COPY instead of ADD:** `ADD` has special behavior (auto-extracts archives,
fetches URLs) that can cause unexpected results. Use `COPY` for local files unless you
need ADD's special features.

**DL3025 — Use JSON-array form for ENTRYPOINT/CMD:** Use `CMD ["node", "app.js"]` instead
of `CMD node app.js`. The shell form wraps the command in `/bin/sh -c`, which doesn't
handle signals correctly.

**DL3042 — Use --no-install-recommends:** Always add `--no-install-recommends` to
`apt-get install` to avoid pulling recommended but unnecessary packages.

**DL4006 — Set SHELL for RUN --mount patterns:** When using `RUN --mount=type=cache`,
set the SHELL to use `-e` flag for proper error handling.

### Why This Specific Approach

Hadolint runs BEFORE the build, providing fast feedback without consuming build minutes.
Catching issues like missing `USER` directive or un-pinned base images early prevents
security problems from reaching production.

The SARIF upload ensures Dockerfile quality issues appear in GitHub's Security tab
alongside other vulnerability alerts. This gives a centralized view of all repository
security concerns.

---

## 7. Job 3: metadata

### YAML Block

```yaml
metadata:
  needs: docker-setup
  runs-on: ubuntu-latest
  outputs:
    tags:     ${{ steps.meta.outputs.tags }}
    labels:   ${{ steps.meta.outputs.labels }}
    json:     ${{ steps.meta.outputs.json }}
    version:  ${{ steps.meta-latest.outputs.version || steps.meta.outputs.version }}
    digest:   ${{ steps.meta.outputs.digest }}
  steps:
    - uses: actions/checkout@v4

    - name: Generate Docker metadata
      id: meta
      uses: docker/metadata-action@v5
      with:
        images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
        labels: |
          org.opencontainers.image.title=${{ github.event.repository.name }}
          org.opencontainers.image.description=Docker Full Lifecycle workflow demo image
          org.opencontainers.image.vendor=${{ github.repository_owner }}
          org.opencontainers.image.licenses=MIT
          maintainer=${{ github.repository_owner }}
        tags: |
          type=ref,event=branch
          type=ref,event=pr
          type=semver,pattern={{version}}
          type=semver,pattern={{major}}.{{minor}}
          type=semver,pattern={{major}}
          type=sha,format=short
          type=raw,value=latest,enable={{is_default_branch}}
          type=raw,value=edge,enable=${{ github.ref == 'refs/heads/dev' }}
        flavor: |
          latest=false
          prefix=
          suffix=

    - name: Extract fallback version
      id: meta-latest
      run: |
        if [ -z "${{ steps.meta.outputs.version }}" ]; then
          VERSION=$(node -p "try{require('./package.json').version}catch(e){'latest'}" 2>/dev/null || echo "latest")
          echo "version=${VERSION}" >> "$GITHUB_OUTPUT"
        else
          echo "version=${{ steps.meta.outputs.version }}" >> "$GITHUB_OUTPUT"
        fi

    - name: Print generated metadata
      run: |
        echo "Tags:"
        echo "${{ steps.meta.outputs.tags }}" | tr ',' '\n' | sed 's/^/  /'
        echo "Labels:"
        echo "${{ steps.meta.outputs.labels }}" | tr ',' '\n' | sed 's/^/  /'
        echo "Version: ${{ steps.meta-latest.outputs.version || steps.meta.outputs.version }}"
```

### Line-by-Line Explanation

**`outputs:`** — Declares what this job produces for downstream consumption.

**`tags: ${{ steps.meta.outputs.tags }}`** — The generated Docker tags as a
comma-separated string (e.g., `ghcr.io/owner/repo:main,ghcr.io/owner/repo:sha-abc123`).

**`labels: ${{ steps.meta.outputs.labels }}`** — OCI labels as a comma-separated string
(e.g., `org.opencontainers.image.created=2024-01-01T00:00:00Z,...`).

**`json: ${{ steps.meta.outputs.json }}`** — Full JSON output including all metadata.

**`version: ${{ steps.meta-latest.outputs.version || steps.meta.outputs.version }}`** —
The detected version. Uses short-circuit evaluation: if `meta-latest` produced a version,
use it; otherwise fall back to `meta` step's version. This handles the case where no
git tag exists.

**`uses: docker/metadata-action@v5`** — Docker's official metadata generation action.
It reads Git context and generates OCI-compliant tags and labels.

**`images:`** — The base image name. All generated tags are prefixed with this. For
example, with `images: ghcr.io/owner/repo`, a `type=sha` tag produces
`ghcr.io/owner/repo:sha-abc123`.

**`labels:`** — Custom OCI labels to apply. The action also auto-generates these labels:
- `org.opencontainers.image.created` — RFC 3339 build timestamp
- `org.opencontainers.image.source` — Repository URL
- `org.opencontainers.image.version` — Detected version
- `org.opencontainers.image.revision` — Git commit SHA
- `org.opencontainers.image.licenses` — From repository
- `org.opencontainers.image.title` — Image title
- `org.opencontainers.image.description` — Repository description
- `org.opencontainers.image.ref.name` — Git reference name

**`tags:`** — Tag generation strategy. Each line is a tag rule.

**`type=ref,event=branch`** — Creates a tag from the branch name. For the `main`
branch, this produces `ghcr.io/owner/repo:main`.

**`type=ref,event=pr`** — Creates a tag from the PR number. For PR #42, this
produces `ghcr.io/owner/repo:pr-42`.

**`type=semver,pattern={{version}}`** — From a Git tag like `v1.2.3`, produces
`ghcr.io/owner/repo:1.2.3`. The `v` prefix is stripped automatically.

**`type=semver,pattern={{major}}.{{minor}}`** — Produces `1.2` from `v1.2.3`.
Range tags allow users to pull the latest patch of a specific minor version.

**`type=semver,pattern={{major}}`** — Produces `1` from `v1.2.3`. Major-only tags
let users track the latest major release.

**`type=sha,format=short`** — Produces `sha-abc123` from the commit SHA. Short format
is 7 characters.

**`type=raw,value=latest,enable={{is_default_branch}}`** — The `latest` tag, but only
on the default branch. The `enable` condition prevents non-main branches from gaining
the `latest` tag.

**`type=raw,value=edge,enable=${{ github.ref == 'refs/heads/dev' }}`** — An `edge`
tag for the dev branch, enabling bleeding-edge image pulls.

**`flavor:`** — Controls automatic tag behavior.

**`latest=false`** — Prevents the action from auto-adding `latest`. We manage `latest`
explicitly with the `type=raw` rule above.

**`prefix=`** and **`suffix=`** — No prefix or suffix added to tags.

**`Extract fallback version:`** — A pure shell step that extracts a version from
`package.json` when no Git tag exists. This ensures downstream jobs always have a
`version` output.

**`echo "version=${VERSION}" >> "$GITHUB_OUTPUT"`** — Sets the step output `version`.
The `$GITHUB_OUTPUT` file is a GitHub Actions convention for setting step outputs.

### docker/metadata-action@v5 — Full Capability Reference

Key inputs:
| Input | Default | Description |
|---|---|---|
| `images` | (required) | Base image name(s), space-separated |
| `tags` | — | Tag generation rules |
| `labels` | — | Custom labels |
| `flavor` | — | Tag flavor (latest, prefix, suffix) |
| `sep-tags` | `,` | Separator for multi-tag output |
| `sep-labels` | `,` | Separator for multi-label output |
| `bake-target` | `gha-docker` | Bake target file |
| `github-token` | GITHUB_TOKEN | Token for API access |

Tag types:
| Type | Example | Description |
|---|---|---|
| `type=ref,event=branch` | `main` | Branch reference |
| `type=ref,event=pr` | `pr-42` | Pull request number |
| `type=ref,event=tag` | `v1.2.3` | Git tag (raw) |
| `type=semver,pattern={{version}}` | `1.2.3` | Semantic version parsing |
| `type=sha` | `sha-a1b2c3d` | Commit SHA |
| `type=raw,value=my-tag` | `my-tag` | Custom static tag |
| `type=schedule` | `nightly` | Scheduled run tag |
| `type=match,pattern=...` | — | Regex match group |
| `type=pep440,pattern={{version}}` | — | Python PEP 440 |

### Why This Specific Approach

Centralized metadata generation ensures ALL downstream jobs use consistent tags and labels.
Without this, the build-push job, release job, and any notification steps would each need
to implement their own tagging logic, leading to drift and inconsistency.

The multi-level semver scheme (version, major.minor, major) gives consumers flexibility:
- `docker pull myimage:1.2.3` — Pin to exact version
- `docker pull myimage:1.2` — Get latest patch of 1.2
- `docker pull myimage:1` — Get latest minor of 1

---

## 8. Job 4: build-push

### YAML Block

```yaml
build-push:
  needs: [metadata, docker-lint]
  runs-on: ubuntu-latest
  outputs:
    digest: ${{ steps.build.outputs.digest }}
    tags: ${{ steps.build.outputs.tags }}
    image-with-digest: ${{ steps.build.outputs.digest && format('{0}@{1}', env.REGISTRY, steps.build.outputs.digest) || steps.build-full-ref.outputs.ref }}
  steps:
    - uses: actions/checkout@v4

    - name: Log in to GitHub Container Registry
      uses: docker/login-action@v3
      with:
        registry: ${{ env.REGISTRY }}
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}

    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3
      with:
        driver: docker-container

    - name: Build and push multi-platform image
      id: build
      uses: docker/build-push-action@v6
      with:
        context: .
        file: ./Dockerfile
        platforms: ${{ github.event.inputs.platforms || 'linux/amd64,linux/arm64' }}
        push: true
        tags: ${{ needs.metadata.outputs.tags }}
        labels: ${{ needs.metadata.outputs.labels }}
        provenance: true
        sbom: true
        cache-from: type=gha
        cache-to: type=gha,mode=max
        build-args: |
          BUILDKIT_CONTEXT_KEEP_GIT_DIR=1
          VERSION=${{ needs.metadata.outputs.version }}
        annotations: ${{ needs.metadata.outputs.labels }}

    - name: Output image reference
      id: build-full-ref
      run: |
        echo "ref=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ steps.build.outputs.digest }}" >> "$GITHUB_OUTPUT"
        echo "Image built and pushed successfully"
        echo "  Registry: ${{ env.REGISTRY }}"
        echo "  Image: ${{ env.IMAGE_NAME }}"
        echo "  Digest: ${{ steps.build.outputs.digest }}"
        echo "  Tags: ${{ needs.metadata.outputs.tags }}"
        echo "  Platforms: ${{ github.event.inputs.platforms || 'linux/amd64,linux/arm64' }}"
```

### Line-by-Line Explanation

**`needs: [metadata, docker-lint]`** — Depends on both the metadata and docker-lint jobs.
This ensures linting passes before we invest CI minutes in building.

**`image-with-digest: ${{ steps.build.outputs.digest && format(...) || steps.build-full-ref.outputs.ref }}`** —
A defensive expression that produces the full image reference with digest. Uses short-circuit
evaluation: if `digest` is set, format the full reference; otherwise, use the fallback output.

**`uses: docker/login-action@v3`** — Authenticates with the container registry. For GHCR,
the credentials are:
- `username: ${{ github.actor }}` — The GitHub user who triggered the workflow
- `password: ${{ secrets.GITHUB_TOKEN }}` — The auto-generated token

The GITHUB_TOKEN's scope is determined by the `permissions` block. Since we set
`packages: write`, this token has push access to GHCR.

**`uses: docker/build-push-action@v6`** — The core build action. It orchestrates the
entire Docker build process using BuildKit.

**`context: .`** — The Docker build context directory. This is sent to the BuildKit
daemon as the build input. Only files within the context are available during the build.

**`file: ./Dockerfile`** — Path to the Dockerfile, relative to the context directory.

**`platforms: ${{ github.event.inputs.platforms || 'linux/amd64,linux/arm64' }}`** —
Target platforms. When `workflow_dispatch` provides platforms, use them; otherwise
default to `linux/amd64,linux/arm64`. BuildKit builds each platform in parallel.

**`push: true`** — Push the image to the registry after build. The push includes both
the platform-specific images and the multi-arch manifest list.

**`tags: ${{ needs.metadata.outputs.tags }}`** — The tags from the metadata job.

**`labels: ${{ needs.metadata.outputs.labels }}`** — OCI labels from the metadata job.

**`provenance: true`** — Generates SLSA Build Level 2 provenance attestation as an
in-image layer. This creates an attestation manifest that records:
- Builder ID (GitHub Actions runner)
- Build configuration (workflow file, inputs)
- Source repository and commit SHA
- Image digest
- Build timestamps

The attestation is stored in the registry as a separate manifest linked to the image.
It can be viewed with `docker buildx imagetools inspect <image>`.

**`sbom: true`** — Generates a Software Bill of Materials as an in-image layer. This
records all packages installed in the image, including:
- OS packages (from apt, apk, yum, etc.)
- Language-specific packages (npm, pip, gem, etc.)
- Package versions and licenses

Setting both `provenance` and `sbom` to `true` is equivalent to passing
`--attest type=provenance` and `--attest type=sbom` to the `docker buildx build` command.

**`cache-from: type=gha`** — Restores cached layers from GitHub Actions cache at the
start of the build. This significantly speeds up subsequent builds when only small
changes have been made.

**`cache-to: type=gha,mode=max`** — Saves build cache to GitHub Actions cache at the
end of the build. `mode=max` exports ALL intermediate layers, maximizing cache reuse.

Cache types:
| Type | Backend | Best for |
|---|---|---|
| `gha` | GitHub Actions cache | Simple CI, no external infra |
| `registry` | Container registry | Shared across CI systems |
| `local` | Local filesystem | Self-hosted runners |
| `s3` | AWS S3 | Enterprise CI |
| `azblob` | Azure Blob Storage | Azure-native CI |

**`build-args:`** — Build arguments passed to the Dockerfile via `ARG` instructions.
`BUILDKIT_CONTEXT_KEEP_GIT_DIR=1` preserves the `.git` directory in the build context,
which is useful for extracting version information during the build.

**`annotations: ${{ needs.metadata.outputs.labels }}`** — Additional annotations for
the image manifest. These are embedded as OCI annotations in the manifest metadata.

### Key Outputs

**`digest`** — The SHA256 digest of the multi-arch manifest list. This is NOT the
digest of the platform-specific image — it references the OCI index (manifest list)
that points to each platform's manifest.

Example digest: `sha256:a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1`

### docker/build-push-action@v6 — Full Capability Reference

Key inputs (in addition to those used above):
| Input | Description |
|---|---|
| `target` | Multi-stage build target |
| `no-cache` | Disable layer caching |
| `pull` | Always pull base images |
| `network` | Build network mode |
| `secret-files` | Mount secret files securely |
| `secrets` | Build secrets (env vars) |
| `ssh` | SSH agent forwarding |
| `extra-from` | Source images for COPY --from |
| `github-token` | GitHub token for authentication |
| `export-cache` | Export cache to additional backends |
| `import-cache` | Import cache from additional backends |
| `outputs` | Build outputs (type=local, type=tar, etc.) |

### Why This Specific Approach

The combination of `provenance: true` and `sbom: true` is significant because these
attestations are generated DURING the build, not after. BuildKit has access to all
the information it needs (every `RUN` command, every installed package) at build time.
Post-build SBOM generation (like we do with anchore/sbom-action) analyzes the final
image and may miss intermediate build artifacts or multi-stage build details.

The GHA cache backend (`type=gha`) is chosen over `type=registry` because:
- No additional storage cost (uses existing GHA cache allotment)
- Automatic cache key management (no manual invalidation)
- Works without registry authentication
- Cache is isolated to the repository

The tradeoff: GHA cache is shared across ALL workflows in the repository, so a
cache-intensive workflow could evict Docker layer caches.

---

## 9. Job 5: image-scan

### YAML Block

```yaml
image-scan:
  needs: build-push
  runs-on: ubuntu-latest
  if: ${{ github.event.inputs.skip-scan != 'true' }}
  steps:
    - uses: actions/checkout@v4

    - name: Log in to GitHub Container Registry
      uses: docker/login-action@v3
      with:
        registry: ${{ env.REGISTRY }}
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}

    - name: Run Trivy vulnerability scanner
      uses: aquasecurity/trivy-action@master
      with:
        scan-type: image
        scan-ref: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}
        format: sarif
        output: trivy-results.sarif
        exit-code: 1
        severity: ${{ env.TRIVY_SEVERITY }}
        vuln-type: os,library
        ignore-unfixed: true
        scanners: vuln,secret

    - name: Upload Trivy SARIF results
      if: always()
      uses: github/codeql-action/upload-sarif@v3
      with:
        sarif_file: trivy-results.sarif
        category: trivy

    - name: Run Docker Scout
      id: scout
      uses: docker/scout-action@v1
      with:
        command: quickview,recommendations
        image: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}
        severity: ${{ env.TRIVY_SEVERITY }}
        github-token: ${{ secrets.GITHUB_TOKEN }}
        exit-code: true

    - name: Print scan summary
      if: always()
      run: |
        echo "=== Trivy Scan Summary ==="
        echo "Image: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}"
        echo "Severity threshold: ${{ env.TRIVY_SEVERITY }}"
        echo "SARIF results uploaded to GitHub Security tab"
```

### Line-by-Line Explanation

**`if: ${{ github.event.inputs.skip-scan != 'true' }}`** — Conditionally skips this
entire job when the `skip-scan` input is set to `true`. The comparison is a string
comparison because workflow dispatch inputs are always strings, even for boolean types.

**`uses: aquasecurity/trivy-action@master`** — The official Trivy action from Aqua Security.
Trivy (pronounced "trivee") is a comprehensive vulnerability scanner for containers.

**`scan-type: image`** — Tells Trivy to scan a container image. Other modes:
- `fs` — Filesystem scan (IaC misconfigurations, secrets)
- `repo` — Git repository scan
- `config` — Kubernetes/YAML/Terraform config scanning
- `sbom` — SBOM file scanning

**`scan-ref:`** — The target to scan. Using `@digest` ensures we scan exactly the image
that was built, not a different image that might have been pushed to the same tag.

**`format: sarif`** — SARIF output for GitHub Security tab integration. Other formats:
- `table` — Human-readable table (best for local runs)
- `json` — Machine-readable JSON
- `template` — Custom Go template

**`exit-code: 1`** — Exit with code 1 when vulnerabilities are found at the specified
severity level. Setting to `0` would report findings without failing the build.

**`severity: ${{ env.TRIVY_SEVERITY }}`** — Only report vulnerabilities at CRITICAL
and HIGH severity. This prevents the build from failing on MEDIUM and LOW findings.

**`vuln-type: os,library`** — Scan both OS-level packages (apt, apk, rpm) and
application libraries (npm, pip, gem, etc.).

**`ignore-unfixed: true`** — Only report vulnerabilities that have a fix available.
This reduces noise from vulnerabilities where no patch exists yet.

**`scanners: vuln,secret`** — Enable vulnerability scanning and secret detection.
Secret detection looks for hardcoded credentials, API keys, and tokens in the image.

**`if: always()`** — Run this step even if previous steps failed. This ensures SARIF
results are uploaded even when Trivy finds vulnerabilities and exits with code 1.

**`uses: docker/scout-action@v1`** — Docker's own image analysis tool. Docker Scout
goes beyond CVE scanning to provide contextual recommendations.

**`command: quickview,recommendations`** — Run two Scout commands:
- `quickview` — Summary of vulnerabilities by severity
- `recommendations` — Suggestions for reducing vulnerabilities (e.g., base image upgrades)

**`exit-code: true`** — Exit with non-zero if findings exceed the severity threshold.

### Trivy vs Docker Scout: Complementary Approaches

| Aspect | Trivy | Docker Scout |
|---|---|---|
| Database | NVD, GHSA, OSV, RedHat, etc. | Docker's own CVE database |
| Speed | Fast (compiled Go binary) | Moderate (cloud analysis) |
| Policy engine | Custom scripts | Built-in policies |
| Recommendations | No (just reports) | Yes (actionable fixes) |
| Format | Multiple (SARIF, JSON, table) | Text/report |
| Licensing | Open source (Apache 2.0) | Free tier with limits |

Running both scanners provides defense in depth. One tool's database may contain CVEs
the other hasn't indexed yet, and Docker Scout's recommendations provide actionable
remediation steps that Trivy doesn't.

### Trivy Severity Levels

| Level | Meaning | Example |
|---|---|---|
| CRITICAL | Exploitation is trivial, widespread damage | RCE in network-facing service |
| HIGH | Exploitation is possible, significant impact | SQL injection, auth bypass |
| MEDIUM | Specific conditions required | XSS with CSP, local privilege escalation |
| LOW | Limited impact, hard to exploit | Information disclosure via error messages |
| UNKNOWN | Severity not yet rated | New CVE without CVSS score |

### Why This Specific Approach

The `exit-code: 1` setting turns Trivy findings into a build gate — if CRITICAL or HIGH
vulnerabilities exist, the workflow fails. This prevents vulnerable images from reaching
the release stage.

The `if: always()` on SARIF upload is critical: even when Trivy fails the build, we
want the vulnerability data to appear in GitHub's Security tab for triage and tracking.

The `skip-scan` bypass exists for emergency hotfixes (e.g., patching a critical
vulnerability in production). In that scenario, the fix itself addresses the CVE, so
scanning would be redundant. However, this creates a paper trail — every bypass is
visible in the workflow run history.

---

## 10. Job 6: sbom-attest

### YAML Block

```yaml
sbom-attest:
  needs: build-push
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Log in to GitHub Container Registry
      uses: docker/login-action@v3
      with:
        registry: ${{ env.REGISTRY }}
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}

    - name: Generate SBOM
      id: sbom
      uses: anchore/sbom-action@v0
      with:
        image: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}
        format: spdx-json
        output-file: ${{ github.event.repository.name }}-sbom.spdx.json
        github-token: ${{ secrets.GITHUB_TOKEN }}

    - name: Install Cosign
      uses: sigstore/cosign-installer@v3
      with:
        cosign-release: 'v2.4.1'

    - name: Sign container image with Cosign keyless signing
      env:
        COSIGN_EXPERIMENTAL: false
      run: |
        cosign sign \
          ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }} \
          --yes \
          --annotations "repo=${{ github.repository }}" \
          --annotations "workflow=${{ github.workflow }}" \
          --annotations "ref=${{ github.ref }}"

    - name: Sign SBOM with Cosign
      run: |
        cosign attest-blob \
          ${{ github.event.repository.name }}-sbom.spdx.json \
          --yes \
          --sign ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}

    - name: Attach build provenance
      uses: actions/attest-build-provenance@v2
      with:
        subject-name: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
        subject-digest: ${{ needs.build-push.outputs.digest }}
        push-to-registry: true
        github-token: ${{ secrets.GITHUB_TOKEN }}

    - name: Upload SBOM and attestation artifacts
      uses: actions/upload-artifact@v4
      with:
        name: sbom-and-attestation
        path: |
          ${{ github.event.repository.name }}-sbom.spdx.json
          ${{ github.event.repository.name }}-sbom.spdx.json.bundle
        retention-days: 90
```

### Line-by-Line Explanation

**`uses: anchore/sbom-action@v0`** — Anchore's SBOM generation action. It uses Syft
(an open-source SBOM tool) to generate a detailed inventory of the container image.

**`format: spdx-json`** — Output format. SPDX (Software Package Data Exchange) is
an ISO standard (ISO/IEC 5962:2021) for SBOM exchange. The JSON variant is the most
machine-readable format. Other formats:
- `cyclonedx-json` — CycloneDX standard (OWASP)
- `spdx-tag-value` — SPDX tag:value format (more human-readable but harder to parse)

**`output-file:`** — Path for the generated SBOM file. Named after the repository
for clarity: `my-repo-sbom.spdx.json`.

**`image:`** — The image to analyze. Using `@digest` for immutable reference.

**`uses: sigstore/cosign-installer@v3`** — Installs the Cosign binary. Cosign is part
of the Sigstore project, which provides a suite of tooling for software supply chain
security.

**`cosign-release: 'v2.4.1'`** — Pins a specific Cosign version. This ensures
reproducible behavior across workflow runs. Version 2.4.1 is a stable release with
keyless signing GA since v2.0.

### Cosign Keyless Signing — Deep Dive

**What happens during `cosign sign`:**

1. **OIDC token request:** Cosign requests an OIDC token from GitHub Actions. The
   token's identity includes:
   - Repository: `github.com/owner/repo`
   - Workflow: `.github/workflows/docker-full-lifecycle.yml`
   - Ref: `refs/heads/main`

2. **Fulcio certificate exchange:** Cosign sends the OIDC token to Fulcio (Sigstore's
   certificate authority). Fulcio verifies the token with GitHub's OIDC provider and
   issues a short-lived X.509 code signing certificate. The certificate includes:
   - Subject: The OIDC identity (workflow identity)
   - Issuer: `https://token.actions.githubusercontent.com`
   - Validity: ~10 minutes
   - Public key: An ephemeral key pair generated by Cosign

3. **Signature generation:** Cosign:
   - Generates an ephemeral key pair (private + public)
   - Signs the image digest with the private key
   - Wraps the signature, public key, and certificate in a standard container
     signature format
   - Uploads the signature to the container registry as a separate manifest

4. **Rekor transparency log:** Cosign creates an entry in Rekor (Sigstore's
   transparency log). This provides:
   - Public auditability (anyone can search Rekor for signatures)
   - Timestamp proof (the signature existed at a specific time)
   - Resilience against key compromise (old signatures remain valid)

**Why this is called "keyless":** The private key is ephemeral — it exists only in
memory during the signing operation and is never stored. The public key is embedded
in the signing certificate, which is signed by Fulcio's root CA. No one needs to
manage, rotate, or distribute long-lived signing keys.

**`cosign attest-blob`** — Signs an arbitrary file (blob) and produces an attestation
bundle. Unlike `cosign sign` which attaches a signature to a container, this produces
a standalone `.bundle` file.

**`--sign ${{ env.REGISTRY }}/...@digest`** — Links the blob attestation to the
specific container image. This proves the SBOM belongs to this exact image.

**`uses: actions/attest-build-provenance@v2`** — GitHub's own attestation mechanism.
This is separate from Cosign and provides:
- SLSA Build Level 2 provenance
- Integration with GitHub's attestation API
- Verifiable through GitHub's trusted services

**`subject-name:`** and **`subject-digest:`** — Identify the artifact being attested.
These must match exactly for verification to succeed.

**`push-to-registry: true`** — Pushes the attestation alongside the image in GHCR.
This stores the attestation as an OCI artifact in the same repository as the image.

### SBOM Format Comparison

| Aspect | SPDX | CycloneDX |
|---|---|---|
| Standard body | Linux Foundation (ISO/IEC 5962) | OWASP |
| Latest version | 2.3 | 1.6 |
| Focus | Legal/license compliance | Security vulnerability correlation |
| Fields | Package names, versions, licenses, relationships | Everything in SPDX plus: vulnerabilities, exploits, risk scores |
| Vulnerability mapping | External references | Built-in vulnerability section |
| Tool support | Broad (Syft, Trivy, Fossa) | Broad (Syft, OWASP tools) |
| GitHub integration | Supported | Supported |

SPDX is chosen here because it's the more established standard with broader GitHub
integration, but both formats serve the same fundamental purpose.

### Why This Specific Approach

Three separate signing/attestation mechanisms provide defense in depth:
1. **Cosign sign:** Standard Sigstore signature for the container image
2. **Cosign attest-blob:** Signed attestation linking the SBOM to the image
3. **GitHub attestation:** SLSA provenance through GitHub's infrastructure

Each mechanism uses a different trust root, so compromise of any one doesn't affect
the others. This is particularly important for regulated environments where you need
to prove an artifact's provenance through multiple independent channels.

---

## 11. Job 7: verify-image

### YAML Block

```yaml
verify-image:
  needs: [build-push, sbom-attest]
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Log in to GitHub Container Registry
      uses: docker/login-action@v3
      with:
        registry: ${{ env.REGISTRY }}
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}

    - name: Pull image by digest
      run: |
        docker pull ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}
        echo "Successfully pulled image by digest"

    - name: Inspect multi-arch manifest list
      run: |
        echo "=== Manifest List ==="
        docker buildx imagetools inspect ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}
        echo ""
        echo "=== Platform Breakdown ==="
        docker buildx imagetools inspect --raw ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }} | jq -r '.manifests[] | "  \(.platform.os)/\(.platform.architecture) → \(.digest)"' 2>/dev/null || echo "  (jq not available, raw output above)"

    - name: Verify Cosign signature
      run: |
        cosign verify \
          ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }} \
          --certificate-identity-regexp "https://github.com/${{ github.repository }}/.github/workflows/.*@${{ github.ref }}" \
          --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
          --verbose
        echo "Signature verification passed"

    - name: Docker Scout final check
      uses: docker/scout-action@v1
      with:
        command: quickview
        image: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}
        github-token: ${{ secrets.GITHUB_TOKEN }}

    - name: Print verification summary
      run: |
        echo "=== Image Verification Summary ==="
        echo "Status: PASSED"
        echo "Image: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}"
        echo "Signature: Verified (Cosign keyless)"
        echo "Multi-arch: Confirmed"
        echo "Scout check: Passed"
        echo ""
        echo "Pull command: docker pull ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}"
```

### Line-by-Line Explanation

**`docker pull ...@digest`** — Pulls the image using its content-addressable digest
rather than a mutable tag. This guarantees we get exactly the bytes that were built
and pushed.

**`docker buildx imagetools inspect`** — Shows the OCI index (manifest list) for a
multi-arch image. Output example:
```
Name:      ghcr.io/owner/repo@sha256:abc...
MediaType: application/vnd.oci.image.index.v1+json
Manifests:
  [0] linux/amd64  digest: sha256:def...
  [1] linux/arm64  digest: sha256:ghi...
```

**`docker buildx imagetools inspect --raw`** — Shows the raw JSON of the manifest list.
Piped through `jq` to extract just the platform information in a readable format.

**`cosign verify`** — Verifies the Cosign signature on the image. In keyless mode, this:
1. Fetches the signature from the registry
2. Validates the certificate chain (ephemeral cert → Fulcio intermediate → Fulcio root)
3. Checks that the certificate's OIDC identity matches the expected workflow identity
4. Verifies the Rekor transparency log entry
5. Confirms the signature covers the image digest

**`--certificate-identity-regexp`** — A regex pattern for the expected identity.
Instead of matching an exact identity (which would include the specific workflow run),
we use regex to match any workflow in this repository on this branch.

**`--certificate-oidc-issuer "https://token.actions.githubusercontent.com"`** —
Verifies that the OIDC token was issued by GitHub Actions, not by a different
OIDC provider. This prevents identity spoofing.

### Why Verify After Push?

Between the push and the verification, a sophisticated attacker could:
1. Overwrite the image tag with a compromised image
2. Tamper with the registry storage backend
3. Exploit a registry vulnerability to swap manifests

By pulling BY DIGEST (not tag) and verifying the signature against the identity,
we detect all of these scenarios:
- Digest mismatch → pull fails or signature verification fails
- Tag overwrite → irrelevant, we use the digest
- Registry tampering → signature validation catches it

---

## 12. Job 8: release

### YAML Block

```yaml
release:
  needs: [verify-image, image-scan]
  runs-on: ubuntu-latest
  if: ${{ github.ref == 'refs/heads/main' || github.event_name == 'release' }}
  steps:
    - uses: actions/checkout@v4

    - name: Download all artifacts
      uses: actions/download-artifact@v4
      with:
        path: release-artifacts/
        merge-multiple: true

    - name: List release artifacts
      run: |
        echo "=== Release Artifacts ==="
        find release-artifacts/ -type f -ls

    - name: Create GitHub Release
      uses: softprops/action-gh-release@v2
      with:
        tag_name: ${{ github.event_name == 'release' && github.event.release.tag_name || format('v{0}', needs.metadata.outputs.version) }}
        name: Release ${{ needs.metadata.outputs.version }}
        body: |
          ## Docker Image

          ### Pull by digest (recommended — immutable):
          ```bash
          docker pull ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}
          ```

          ### Pull by tag:
          ```bash
          docker pull ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ needs.metadata.outputs.version }}
          ```
          ...
        files: |
          release-artifacts/**/*
        draft: ${{ github.event_name != 'release' }}
        prerelease: ${{ !startsWith(github.ref, 'refs/tags/v') }}
        generate_release_notes: true
        make_latest: true
      env:
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### Line-by-Line Explanation

**`if: ${{ github.ref == 'refs/heads/main' || github.event_name == 'release' }}`** —
Only create a release on main branch pushes or when triggered by a GitHub Release
event. This prevents every dev/feature branch push from creating a release.

**`uses: actions/download-artifact@v4`** — Downloads previously uploaded artifacts
from the sbom-attest job (and any other artifacts).

**`path: release-artifacts/`** — Directory to store downloaded artifacts.

**`merge-multiple: true`** — When downloading multiple artifacts, merge them into a
single directory instead of creating separate subdirectories per artifact.

**`uses: softprops/action-gh-release@v2`** — A popular community action for creating
and managing GitHub Releases.

**`tag_name:`** — The Git tag for the release. When triggered by a `release` event, use
the existing release's tag. For `workflow_dispatch`, create a new tag from the version.

**`draft: ${{ github.event_name != 'release' }}`** — Create as a draft when manually
triggered, allowing review before publication.

**`generate_release_notes: true`** — Automatically generate release notes from commit
history since the last release.

**`make_latest: true`** — Mark this release as the "latest" release.

**`files:`** — Glob pattern for files to attach to the release. All downloaded
artifacts are included.

### Why This Specific Approach

The conditional behavior (draft vs. published) handles two distinct use cases:
1. Triggered by a `release` event — artifacts are attached to the existing published release
2. Triggered by `workflow_dispatch` — creates a draft release for review

The release body includes Docker pull commands with both digest and tag variants,
making it easy for consumers to pull the correct image.

---

## 13. Job 9: cleanup

### YAML Block

```yaml
cleanup:
  needs: release
  runs-on: ubuntu-latest
  if: ${{ github.ref == 'refs/heads/main' }}
  steps:
    - name: Delete untagged package versions
      uses: actions/delete-package-versions@v5
      with:
        package-name: ${{ env.IMAGE_NAME }}
        package-type: container
        min-versions-to-keep: 5
        delete-only-untagged-versions: true
        token: ${{ secrets.GITHUB_TOKEN }}

    - name: Report cleanup
      run: |
        echo "=== Package Cleanup ==="
        echo "Package: ${{ env.IMAGE_NAME }}"
        echo "Action: Deleted untagged versions"
        echo "Min kept: 5"
        echo "Registry: ${{ env.REGISTRY }}"
```

### Line-by-Line Explanation

**`uses: actions/delete-package-versions@v5`** — GitHub's official action for deleting
old package versions from GitHub Packages.

**`package-name: ${{ env.IMAGE_NAME }}`** — The package to clean up. For GHCR, this is
the same as the image name.

**`package-type: container`** — Specifies the package type. Options include `container`,
`npm`, `maven`, `rubygems`, `nuget`, `docker`.

**`min-versions-to-keep: 5`** — Safety net: never delete below 5 versions. This ensures
you always have a few recent versions available for rollback.

**`delete-only-untagged-versions: true`** — Critical safety flag: only delete "orphaned"
versions that have no tags pointing to them. Tagged versions are preserved.

### When Untagged Versions Are Created

Untagged versions accumulate in GHCR when:
1. A new build pushes with the same tag as a previous build — the old version loses its tag
2. A tag is deleted from the repository — all versions with that tag become untagged
3. A package is migrated between repositories — tags may be lost during migration

Without cleanup, these orphaned versions consume storage quota indefinitely.

### Why This Specific Approach

The `delete-only-untagged-versions: true` flag is the most important safety mechanism.
It prevents accidental deletion of tagged versions that might be referenced in:
- Production deployment manifests
- CI/CD pipelines pulling by tag
- Developer's local Docker caches

The condition `github.ref == 'refs/heads/main'` restricts cleanup to main branch runs,
preventing cleanup jobs on PR or dev branches from interfering with active development.

---

## 14. Docker Concepts Reference

### 14.1 Multi-Architecture Builds (amd64 vs arm64)

**Why two architectures matter:**

| Architecture | Common Name | Typical Hardware |
|---|---|---|
| `linux/amd64` | x86_64 | Intel Xeon, AMD EPYC, Intel Core |
| `linux/arm64` | AArch64 | AWS Graviton, Apple M-series, Ampere Altra |

The industry is shifting toward arm64 for its better performance-per-watt:
- AWS Graviton instances are 20-40% cheaper than equivalent x86 instances
- Apple Silicon (M1/M2/M3/M4) is arm64-based
- Major cloud providers offer arm64 options for all service categories

A Docker image built for amd64 WILL NOT RUN on arm64 without emulation.
Docker images are architecture-specific because they contain compiled binaries.

**How multi-arch images work:**

An OCI image manifest list (also called "fat manifest") is a JSON document that
references multiple platform-specific manifests:

```json
{
  "schemaVersion": 2,
  "mediaType": "application/vnd.oci.image.index.v1+json",
  "manifests": [
    {
      "mediaType": "application/vnd.oci.image.manifest.v1+json",
      "digest": "sha256:amd64-specific-digest",
      "platform": { "architecture": "amd64", "os": "linux" }
    },
    {
      "mediaType": "application/vnd.oci.image.manifest.v1+json",
      "digest": "sha256:arm64-specific-digest",
      "platform": { "architecture": "arm64", "os": "linux" }
    }
  ]
}
```

When a user runs `docker pull ghcr.io/owner/repo:latest`, Docker:
1. Fetches the manifest list
2. Reads the user's CPU architecture (`uname -m`)
3. Selects the matching platform-specific manifest
4. Pulls only that platform's layers

This is transparent to the end user — they always use the same image name, and Docker
handles architecture selection automatically.

**Why QEMU emulation is needed:**

GitHub Actions runners are exclusively amd64 (x86_64). To build arm64 images, we need
either:
1. **Cross-compilation:** Set up cross-compilers for every language in the Dockerfile
2. **QEMU emulation:** Run arm64 binaries transparently through an instruction translator

QEMU emulation is simpler but slower. QEMU translates every arm64 instruction to an
equivalent sequence of x86 instructions at runtime. For CPU-intensive builds (compilation,
package installation), the slowdown is 2-5x.

For frequently built projects, consider:
- GitHub's larger [arm64 hosted runners](https://github.com/features/github-actions)
- Self-hosted arm64 runners (e.g., on AWS Graviton instances)

### 14.2 BuildKit and the docker-container Driver

**What is BuildKit?**

BuildKit is Docker's next-generation build subsystem. It was introduced in Docker 18.09
and became the default in Docker 23.0. Key improvements over the legacy builder:

| Capability | Legacy Builder | BuildKit |
|---|---|---|
| Concurrent builds | Single queue | Parallel |
| Layer caching | Basic | Advanced (multi-backend) |
| Multi-stage builds | Works | Optimized (skips unused stages) |
| SSH mounts | No | Yes |
| Secret mounts | No | Yes (never in image history) |
| Cache mounts | No | Yes (apt, npm, etc.) |
| SBOM/provenance | No | Yes (via attestations) |
| Multi-architecture | Limited | Full |

**How BuildKit works:**

BuildKit uses a client-server architecture:
1. The `buildctl` client (or Docker CLI) sends a build definition to a BuildKit daemon
2. The daemon processes the build as a DAG of operations (not a linear script)
3. Each operation is cached and can be shared across builds
4. Operations run in parallel where dependencies allow

**docker vs docker-container driver:**

The `docker` driver uses BuildKit embedded in the Docker daemon. It's convenient but
limited: the embedded BuildKit shares resources with Docker's runtime operations and
doesn't support advanced features.

The `docker-container` driver launches a dedicated BuildKit container. This container:
- Runs as a separate process with its own resource limits
- Supports all cache export types (gha, registry, local, s3, azblob)
- Can be configured with custom buildkitd.toml
- Supports SBOM and provenance attestations
- Enables multi-architecture builds via QEMU registration

### 14.3 Docker Layer Caching

**How Docker layer caching works:**

Every Dockerfile instruction creates a layer. Docker caches each layer by its content
hash. When building, Docker checks if a layer with the same hash already exists in the
cache. If so, it reuses the cached layer instead of re-executing the instruction.

**Cache invalidation rules:**
1. If a layer's cache misses, all SUBSEQUENT layers also miss (cache chain break)
2. `COPY`/`ADD` layers are invalidated when file contents change
3. `RUN` layers are invalidated when the command or preceding layer changes
4. `ARG`/`ENV` changes invalidate depending on position in Dockerfile

**Optimization strategy — order Dockerfile instructions by change frequency:**
```
# Rarely changes — cached almost always
FROM node:20-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates

# Changes with package.json — cache invalidated when deps change
COPY package.json package-lock.json ./
RUN npm ci --only=production

# Changes on every source edit — last for maximum cache reuse
COPY src/ ./src/
COPY dist/ ./dist/
CMD ["node", "dist/index.js"]
```

**GitHub Actions cache backend (`type=gha`):**

The GHA cache backend stores build cache in GitHub's Actions cache infrastructure.
Key characteristics:
- **Scope:** Repository-level, shared across all workflows
- **Persistence:** Up to 7 days since last access
- **Size limit:** Varies by plan (free: 10GB, paid: included in minutes)
- **Eviction:** Least Recently Used (LRU) when over limit

**`mode=max` vs `mode=min` cache export:**

| Mode | Layers cached | Best for |
|---|---|---|
| `mode=max` | All intermediate layers | High churn, wants max reuse |
| `mode=min` | Only final image layers | Stable Dockerfile, wants smaller cache |

`mode=max` is recommended for CI because:
- It caches ALL intermediate layers, not just the final image
- When one layer changes, only that layer needs rebuilding
- Subsequent builds rebuild in seconds instead of minutes

**Cache backends compared:**

| Backend | Setup | Speed | Sharing | Cost |
|---|---|---|---|---|
| `type=gha` | Zero (built-in) | Fast | Same repo | Free |
| `type=registry` | Registry auth | Medium | Any registry | Registry storage fees |
| `type=local` | Local filesystem | Fastest | Self-hosted runners | Free |
| `type=s3` | AWS credentials | Medium | Cross-CI | S3 storage |
| `type=azblob` | Azure credentials | Medium | Cross-CI | Azure storage |

### 14.4 Manifest Lists and Digest Pinning

**What is a manifest list (OCI index)?**

An OCI image index (commonly called a "manifest list" or "fat manifest") is a JSON
document that references multiple platform-specific manifests. It is the mechanism
that enables `docker pull` to automatically select the right image for any architecture.

**Manifest list structure (OCI format):**

The OCI image index contains:
- `mediaType`: Always `application/vnd.oci.image.index.v1+json`
- `manifests`: Array of descriptor objects, each with:
  - `mediaType`: Reference to the platform-specific manifest
  - `digest`: SHA256 of the platform-specific manifest
  - `size`: Size of the referenced manifest
  - `platform`: OS, architecture, variant (e.g., `linux/arm64/v8`)
  - `annotations`: Optional metadata

**Tag vs digest — fundamental difference:**

| Property | Tag | Digest |
|---|---|---|
| Mutable | Yes (can be overwritten) | No (content-addressed) |
| Human-readable | Yes (`v1.2.3`) | No (`sha256:a1b2...`) |
| Uniqueness | NOT unique (many tags, one image) | Unique (one digest, one image) |
| Security | Tag hijacking possible | Immutable reference |
| Pull syntax | `image:tag` | `image@sha256:...` |

**Why use digest pinning in production:**

1. **Immutability:** An image tagged `v1.2.3` today could be overwritten with different
   content tomorrow. The digest `sha256:a1b2...` always refers to the same content.

2. **Supply chain security:** If an attacker gains write access to the registry, they
   can overwrite tags with compromised images. They cannot change the content behind
   a digest without rebuilding.

3. **Deployment consistency:** Every node in a cluster pulls the exact same image
   content when using digest references. Tag-based pulls could race and get different
   versions if a tag is updated during deployment.

4. **Verification:** Signatures are attached to digests, not tags. A verified signature
   on a digest proves that EXACT content was signed.

### 14.5 OCI Annotations and Labels

OCI annotations are key-value metadata that can be attached to images, manifests, and
indices. They are governed by the [OCI Image Spec](https://github.com/opencontainers/image-spec).

**Standard OCI annotations (pre-defined):**

| Annotation | Description |
|---|---|
| `org.opencontainers.image.created` | Build timestamp (RFC 3339) |
| `org.opencontainers.image.authors` | Contact information |
| `org.opencontainers.image.url` | URL to find more info |
| `org.opencontainers.image.documentation` | URL to documentation |
| `org.opencontainers.image.source` | URL to source code |
| `org.opencontainers.image.version` | Version of the packaged software |
| `org.opencontainers.image.revision` | Source control revision (commit SHA) |
| `org.opencontainers.image.vendor` | Vendor distributing the image |
| `org.opencontainers.image.licenses` | SPDX license identifier |
| `org.opencontainers.image.ref.name` | Reference name (tag-like) |
| `org.opencontainers.image.title` | Human-readable title |
| `org.opencontainers.image.description` | Human-readable description |
| `org.opencontainers.image.base.digest` | Digest of the base image |
| `org.opencontainers.image.base.name` | Reference of the base image |

**How labels are used:**

1. **Discovery:** Users can search for images by label in registries
2. **Compliance:** Labels prove which version and source produced an image
3. **Automation:** Tools can read labels to determine image provenance
4. **Documentation:** Embedded metadata eliminates external lookup

### 14.6 Cosign Keyless Signing

**The Sigstore ecosystem:**

Cosign is part of Sigstore, a set of tools for signing and verifying software. The
ecosystem includes:

| Component | Role |
|---|---|
| **Cosign** | CLI tool for signing container images and blobs |
| **Fulcio** | Certificate Authority that issues short-lived code signing certs |
| **Rekor** | Transparency log for recording signatures |
| **Gitsign** | Git commit signing using Sigstore |
| **Policy Controller** | Kubernetes admission controller for signature verification |

**Keyless signing end-to-end flow:**

```
1. Workflow starts → GitHub generates OIDC token
                         │
2. cosign sign → Requests OIDC token from GitHub
                         │
3. Exchange with Fulcio → OIDC token proves identity
     Fulcio issues short-lived X.509 cert
     Cert includes: public key, OIDC identity, Fulcio chain
                         │
4. Cryptographically sign image digest
     Using ephemeral private key (deleted after signing)
                         │
5. Upload to registry: signature + cert + chain
     Stored as separate manifest linked to image
                         │
6. Rekor entry: hash of signature + cert + timestamp
     Public ledger proves signature existed at this time
```

**What the signature proves:**

When someone verifies the signature, they confirm:
1. The image was signed by a holder of an ephemeral key bound to the OIDC identity
2. The OIDC identity matches the expected workflow/repository
3. The certificate was valid (within its short lifetime) when used
4. The signature was recorded in Rekor at the claimed time

**What it does NOT prove:**
- The image is free of vulnerabilities (use Trivy for that)
- The image was reviewed by a human (two-person review covers that)
- The build was hermetic/reproducible (SLSA L3+ covers that)

### 14.7 SLSA Provenance Levels

**SLSA (Supply-chain Levels for Software Artifacts)** is a security framework that
defines increasing levels of supply chain security:

| Level | Requirements | This workflow |
|---|---|---|
| **L0** | No guarantees | |
| **L1** | Build process documented | Yes (workflow file) |
| **L2** | Signed provenance + OIDC auth | Yes (attest-build-provenance) |
| **L3** | Hosted build + isolation | Partially (GitHub Actions is hosted) |
| **L4** | Hermetic + two-person review + deps complete | No |

Our workflow achieves SLSA Build Level 2 because:
- Provenance is generated as a cryptographically signed attestation
- The attestation uses OIDC identity (not a shared secret)
- The build is hosted on GitHub Actions (not a developer's laptop)
- The source repo and commit are recorded

To reach L3, we would need:
- Build isolation (no network access during build)
- Pre-declared dependencies

To reach L4, we would additionally need:
- Two-person review for all changes
- Hermetic builds (no external network access)
- Complete dependency graph

### 14.8 SBOM (Software Bill of Materials)

**What an SBOM contains:**

An SPDX 2.3 SBOM for a container image includes:

1. **Document information:** Creator (tool), created timestamp, SPDX version
2. **Package information:** For every package in the image:
   - Package name and version
   - Package supplier (who created/curated it)
   - Package download location
   - Package license (SPDX identifier)
   - Package copyright text
   - External references (CVE URLs, homepages)
3. **Relationship information:** How packages relate:
   - `DESCENDANT_OF` — package derives from another
   - `DEPENDENCY_OF` — package is a dependency
   - `CONTAINS` — image contains this package

**Why SBOMs matter for security:**

1. **Vulnerability correlation:** When a new CVE is announced, you can check your SBOMs
   to see if you're affected, without scanning each image individually

2. **License compliance:** Track which open-source licenses your dependencies use

3. **Supply chain transparency:** Know every component in your software, including
   transitive dependencies

4. **Regulatory compliance:** Executive Order 14028 (US) and similar regulations require
   SBOMs for government software

### 14.9 Trivy Vulnerability Scanning

**How Trivy works:**

Trivy maintains a local vulnerability database that aggregates data from:
- NVD (National Vulnerability Database)
- RedHat CVE database
- Debian Security Tracker
- Alpine CVE database
- GitHub Security Advisories (GHSA)
- OSV (Open Source Vulnerabilities)
- AWS ECR vulnerability data
- Go Vulnerability Database
- RustSec Advisory Database
- Photon CVE database
- SUSE CVRF/CVE database
- Ubuntu CVE Tracker
- Chainguard CVE database

For each package in the image, Trivy:
1. Identifies the package name and version
2. Looks up the package in its vulnerability database
3. Returns any CVEs that affect this version
4. Applies severity filters and fix-availability filters
5. Reports the results in the requested format

**Scanners available in Trivy:**

| Scanner | What it detects | Example findings |
|---|---|---|
| `vuln` | Known vulnerabilities | CVE-2024-1234 in curl |
| `secret` | Hardcoded secrets | AWS keys, GitHub tokens |
| `misconfig` | Infrastructure misconfigs | Container running as root |

### 14.10 Docker Scout

**How Docker Scout differs from Trivy:**

Docker Scout is a policy-based analysis tool that:
- Analyzes image layers and package inventory
- Provides policy evaluation (not just CVE listing)
- Offers actionable recommendations (base image upgrades)
- Integrates with Docker Hub and Docker Desktop
- Has a separate vulnerability database

**Scout commands:**

| Command | Description |
|---|---|
| `quickview` | Summary of vulnerabilities by severity |
| `compare` | Compare image against baseline |
| `recommendations` | Suggest actions to reduce vulnerabilities |
| `policy` | Evaluate against organization's security policy |
| `cves` | Detailed CVE information |
| `sync` | Sync image to Scout for remote analysis |

---

## 15. GitHub Actions Concepts Reference

### 15.1 workflow_dispatch with Typed Inputs

`workflow_dispatch` enables manual triggering of workflows with user-provided inputs.
The input types render as native HTML form elements in the GitHub Actions UI:

**String input** renders as a text field:
```yaml
platforms:
  description: 'Target platforms'
  required: false
  default: 'linux/amd64,linux/arm64'
  type: string
```

**Boolean input** renders as a checkbox:
```yaml
skip-scan:
  description: 'Skip vulnerability scan'
  required: false
  default: false
  type: boolean
```

**Choice input** renders as a dropdown:
```yaml
environment:
  description: 'Target environment'
  required: true
  type: choice
  options:
    - staging
    - production
```

Inputs are accessed via `${{ github.event.inputs.<name> }}`. Important: all inputs
are STRINGS, even boolean ones. Compare boolean inputs as strings:
```yaml
if: ${{ github.event.inputs.skip-scan != 'true' }}
```

### 15.2 Permissions Block

The `permissions` block controls the GITHUB_TOKEN's scope. By default, the token has
only `contents: read` in repositories without GitHub Pages.

**Permission scopes used in this workflow:**

| Scope | Operations |
|---|---|
| `contents: write` | Create releases, upload assets, push tags |
| `packages: write` | Push images to GHCR, manage package versions |
| `id-token: write` | Request OIDC token for Cosign/SLSA |
| `attestations: write` | Store build provenance attestations |
| `security-events: write` | Upload SARIF to Security tab |

**Minimal permissions pattern:** Always use the principle of least privilege. Start
with minimal permissions and add only what's needed:

```yaml
permissions:
  contents: read     # Default — checkout source
  # ... add only what your workflow needs
```

### 15.3 Job Outputs

Jobs can pass data to downstream jobs through `outputs`. This is essential for
passing digests, tags, and version information between jobs.

**Defining outputs (in the producing job):**
```yaml
job-name:
  outputs:
    my-output: ${{ steps.my-step.outputs.my-value }}
  steps:
    - id: my-step
      run: echo "my-value=some-data" >> "$GITHUB_OUTPUT"
```

**Consuming outputs (in downstream jobs):**
```yaml
downstream-job:
  needs: job-name
  steps:
    - run: echo "${{ needs.job-name.outputs.my-output }}"
```

**Rules for job outputs:**
1. Outputs must be declared in the `outputs:` block of the job
2. Values come from steps via `$GITHUB_OUTPUT`
3. Outputs are strings only (no complex objects)
4. Outputs are available to any job that declares `needs: <producer>`
5. Outputs are read-only — downstream jobs cannot modify them

### 15.4 Needs (Job Dependencies)

The `needs:` keyword creates a dependency between jobs, forming a Directed Acyclic
Graph (DAG). GitHub Actions automatically parallelizes jobs that have no dependency
relationship.

**Single dependency:**
```yaml
job-b:
  needs: job-a
```
Job-b starts only after job-a completes successfully.

**Multiple dependencies:**
```yaml
job-c:
  needs: [job-a, job-b]
```
Job-c starts only after BOTH job-a and job-b complete.

**Implicit parallelism:** Jobs `docker-lint` and `metadata` both depend on
`docker-setup` but not on each other, so they run in parallel automatically.

**DAG execution rules:**
1. Jobs with no `needs:` start immediately (root-level jobs)
2. Jobs with a single `needs:` start when that job finishes
3. Jobs with multiple `needs:` wait for ALL dependencies to finish
4. If a dependency fails, dependent jobs are skipped (unless `if: always()`)
5. Circular dependencies are detected at parse time and cause an error

### 15.5 if: Conditions

The `if:` keyword controls whether a job or step runs. It evaluates a GitHub
expression and runs only when the expression is truthy.

**Job-level conditions (skip entire job):**
```yaml
image-scan:
  if: ${{ github.event.inputs.skip-scan != 'true' }}
```

**Step-level conditions (skip individual steps):**
```yaml
- name: Upload SARIF
  if: always()  # Run even if previous steps failed
```

**Common conditional expressions:**

| Expression | Evaluation |
|---|---|
| `always()` | Always run, even if dependencies failed |
| `success()` | Run only if all prior steps succeeded (default) |
| `failure()` | Run only if a prior step failed |
| `cancelled()` | Run only if the run was cancelled |
| `github.ref == 'refs/heads/main'` | Only on main branch |
| `startsWith(github.ref, 'refs/tags/')` | Only for tag pushes |
| `github.event_name == 'release'` | Only when triggered by release |
| `contains(github.event.issue.labels.*.name, 'bug')` | Issue has 'bug' label |

**Important:** In YAML, bare `if:` values like `if: always()` might be parsed as
booleans. Always wrap GitHub expressions in `${{ }}`:
```yaml
if: ${{ always() }}
```
Without `${{ }}`, YAML might interpret `always()` as a string or throw an error.

### 15.6 env for Default Values

The `env:` block at workflow, job, or step level sets environment variables:

```yaml
env:
  REGISTRY: ghcr.io           # Workflow-level default
  TRIVY_SEVERITY: CRITICAL,HIGH

job:
  env:
    JOB_VAR: value            # Job-level override
  steps:
    - env:
        STEP_VAR: value       # Step-level override
      run: echo $STEP_VAR
```

**Variable precedence (highest wins):**
1. Step-level `env:` — overrides all
2. Job-level `env:` — overrides workflow defaults
3. Workflow-level `env:` — baseline
4. Environment variable set via `$GITHUB_ENV` in a step

### 15.7 Expression Syntax

**`${{ }}` syntax rules:**

Inside `${{ }}`, you can use:
- Literals: strings (in quotes), numbers, booleans
- Context objects: `github.*`, `env.*`, `needs.*`, `steps.*`, `secrets.*`, `inputs.*`
- Functions: `contains()`, `startsWith()`, `endsWith()`, `format()`, `join()`, `hashFiles()`
- Operators: `==`, `!=`, `&&`, `||`, `!`, `<`, `>`, `+`, `-`, `*`, `/`

**Important rules:**
1. `${{ }}` is evaluated BEFORE the step runs (at parse time for `if:`, at runtime for
   step content)
2. Shell commands inside `run:` that use `${{ }}` have the expressions evaluated before
   the shell sees them
3. Always quote expressions in shell contexts: `echo "${{ env.REGISTRY }}"` (not
   `echo ${{ env.REGISTRY }}` which could break if the value contains spaces)

**`secrets` context:**

Secrets are accessed via `${{ secrets.SECRET_NAME }}`. The GITHUB_TOKEN is always
available as `${{ secrets.GITHUB_TOKEN }}`. Other secrets must be configured in
repository Settings > Secrets and variables > Actions.

**`needs` context for cross-job references:**

```yaml
${{ needs.metadata.outputs.tags }}
${{ needs.build-push.outputs.digest }}
```

The structure is: `needs.<job-id>.outputs.<output-name>`.

### 15.8 OIDC Authentication

**What is OIDC and why is it needed?**

OpenID Connect (OIDC) is an identity layer on top of the OAuth 2.0 protocol. In
GitHub Actions, OIDC allows the workflow to obtain a token that proves its identity
to external services (like Sigstore's Fulcio) WITHOUT storing any long-lived secrets.

**How OIDC works in GitHub Actions:**

```yaml
permissions:
  id-token: write    # Required for OIDC token generation
```

When `id-token: write` is set:
1. GitHub Actions exposes an OIDC token endpoint at a URL stored in the environment
   variable `ACTIONS_ID_TOKEN_REQUEST_URL`
2. The workflow requests a token from this endpoint, providing a proof of the workflow
   run's identity (repository, ref, run ID)
3. External services can verify this token using GitHub's OIDC public keys

**What the OIDC token contains (claims):**

```json
{
  "sub": "repo:owner/repo:ref:refs/heads/main",
  "aud": "sigstore",
  "iss": "https://token.actions.githubusercontent.com",
  "job_workflow_ref": "owner/repo/.github/workflows/workflow.yml@refs/heads/main",
  "runner_environment": "github-hosted",
  "repository": "owner/repo",
  "ref": "refs/heads/main",
  "sha": "commit-sha"
}
```

For Cosign, the critical claims are:
- `job_workflow_ref` — Which workflow file is running
- `repository` — Which repository triggered the run
- `ref` — Which branch/tag triggered the run

These claims are embedded in the Fulcio certificate during signing and extracted
during verification.

---

## Quick Reference: Key Files Created

| File | Purpose |
|---|---|
| `.github/workflows/docker-full-lifecycle.yml` | The workflow definition |
| `.github/workflow-lab/docs/workflow-2-docker-lifecycle.md` | This documentation |

## End of Document

---

## 16. Extended Dockerfile Optimization Guide

### 16.1 Base Image Selection

Choosing the right base image is one of the most consequential decisions in Docker development.
The base image determines the security surface, image size, build time, and runtime behavior.

**Image size comparison (approximate, for a Node.js app):**

| Base Image | Approx Size | Packages | Use Case |
|---|---|---|---|
| `node:22` (full) | ~1.1 GB | Full build toolchain | Development, CI |
| `node:22-slim` | ~250 MB | Minimal + glibc | Production (needs glibc) |
| `node:22-alpine` | ~180 MB | musl libc + apk | Production (smallest) |
| `node:22-bookworm-slim` | ~260 MB | Debian 12 slim | Production (Debian base) |
| `scratch` (distroless) | ~0 MB | Nothing | Go binary, static apps |

**Recommendations:**
- Use `-slim` variants for general production use — they strip unnecessary packages while
  retaining glibc compatibility
- Use Alpine for smallest possible images, but test thoroughly — musl libc can cause
  subtle compatibility issues with native Node.js addons
- Use `bookworm-slim` or `bullseye-slim` (Debian-based) when you need specific apt packages
- Avoid `:latest` — pin to a specific version tag or better, a digest

**Security considerations:**
- Smaller images = fewer packages = smaller attack surface
- Each package in the image is a potential CVE vector
- Alpine images typically have fewer CVEs because they have fewer packages
- Regular base image updates are critical — a patched base image fixes hundreds of CVEs

### 16.2 Multi-Stage Builds

Multi-stage builds use multiple `FROM` statements in a single Dockerfile. Only the final
stage produces the runtime image; earlier stages are for building and can use different
base images with full toolchains.

```dockerfile
# Stage 1: Build
FROM node:22 AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Production
FROM node:22-slim AS production
WORKDIR /app
RUN addgroup --system app && adduser --system app
COPY --from=builder --chown=app:app /app/dist ./dist
COPY --from=builder --chown=app:app /app/node_modules ./node_modules
USER app
EXPOSE 3000
CMD ["node", "dist/index.js"]
```

**Benefits of multi-stage builds:**
1. **Dramatically smaller images:** The final image only contains runtime dependencies, not
   the TypeScript compiler, dev dependencies, or build tools
2. **Different base images per stage:** Use `node:22` (full) for building (needs compiler),
   `node:22-slim` for production (minimal)
3. **Security isolation:** Build tools with known vulnerabilities (like older npm versions)
   are excluded from the final image
4. **COPY --from selects precise artifacts:** Only copy the specific files needed —
   no build context pollution

### 16.3 Layer Optimization Strategies

**Combine related operations to reduce layer count:**

```dockerfile
# BAD — 4 layers, 4x the space for apt lists
RUN apt-get update
RUN apt-get install -y curl
RUN apt-get install -y ca-certificates
RUN rm -rf /var/lib/apt/lists/*

# GOOD — 1 layer, one filesystem snapshot
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*
```

**Leverage Docker cache mounts for package managers:**

```dockerfile
# Cache npm packages across builds (BuildKit only)
RUN --mount=type=cache,target=/root/.npm \
    npm ci --only=production

# Cache apt packages across builds (BuildKit only)
RUN --mount=type=cache,target=/var/cache/apt \
    apt-get update && apt-get install -y curl
```

**Optimize COPY order for maximum cache hits:**

```dockerfile
# 1. First, copy dependency definitions (changes rarely)
COPY package.json package-lock.json ./
# 2. Install dependencies (cached unless package.json changes)
RUN npm ci
# 3. Last, copy source code (changes every commit)
COPY . .
```

### 16.4 Non-Root User Best Practices

Running containers as root is a well-known security antipattern. If an attacker exploits
an application vulnerability in a root-running container, they gain root access to the
container and potentially the host system.

```dockerfile
# Create a non-root user
RUN addgroup --system app && adduser --system --ingroup app app

# Set ownership of application files
COPY --chown=app:app . .

# Switch to the non-root user
USER app
```

**Why this matters:**
- Containers running as root have the same capabilities as root on the host (with caveats)
- A compromised root container can escape to the host via kernel exploits
- Non-root users cannot bind to privileged ports (<1024) — Kubernetes can map them
- Many security scanners (including Trivy) flag root containers as HIGH severity

### 16.5 HEALTHCHECK Instruction

The `HEALTHCHECK` instruction tells Docker how to test if the container is functioning:

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:3000/health || exit 1
```

**Parameters:**
- `--interval=30s`: Check every 30 seconds
- `--timeout=3s`: Each check must complete within 3 seconds
- `--start-period=5s`: Wait 5 seconds before first check (grace period)
- `--retries=3`: Mark as unhealthy after 3 consecutive failures

Health checks enable:
- Docker's orchestration to restart unhealthy containers
- Load balancers to route traffic away from failing instances
- Rollback triggers in deployment systems

### 16.6 Dockerignore File

A `.dockerignore` file excludes files from the Docker build context, similar to
`.gitignore`. This improves build performance and security:

```dockerignore
.git
.gitignore
node_modules/
npm-debug.log*
Dockerfile
.dockerignore
README.md
*.md
test/
tests/
.gitlab-ci.yml
.github/
.vscode/
.idea/
*.log
.env
.env.*
coverage/
dist/          # If building inside Docker, exclude pre-built
```

**Benefits:**
- **Smaller build context:** Faster upload from client to BuildKit daemon
- **Security:** Exclude secrets like `.env` files
- **Cache efficiency:** Excluding unnecessary files prevents cache invalidation from
  unrelated file changes
- **Faster builds:** BuildKit has less data to process

---

## 17. Security Hardening Guide

### 17.1 Defense in Depth Strategy

This workflow implements multiple layers of security:

| Layer | Tool/Mechanism | What It Prevents |
|---|---|---|
| Code analysis | Hadolint (docker-lint) | Dockerfile anti-patterns |
| Vulnerability scan | Trivy (image-scan) | Known CVEs in packages |
| Policy evaluation | Docker Scout (image-scan) | Policy violations |
| Immutable reference | Digest pinning (verify-image) | Tag hijacking |
| Signature verification | Cosign verify (verify-image) | Image tampering |
| Supply chain attestation | SLSA provenance (sbom-attest) | Build origin fraud |
| Component inventory | SBOM (sbom-attest) | Unknown dependencies |

### 17.2 Supply Chain Security Checklist

For a production-grade supply chain security posture, verify all of these:

- [ ] Base images are pinned to specific digests, not tags
- [ ] All apt/apk packages are version-pinned
- [ ] Container runs as non-root user
- [ ] No secrets (API keys, tokens) baked into image layers
- [ ] Layer cache does not leak secrets (use `--mount=type=secret` for BuildKit)
- [ ] Image is scanned for CVEs before every release
- [ ] Image is signed (Cosign) before push
- [ ] SBOM is generated and attached to the release
- [ ] SLSA provenance attestation exists for every release
- [ ] Signature is verified before deployment
- [ ] `.dockerignore` excludes sensitive files
- [ ] Only production dependencies are included in the final image

---

## 18. Troubleshooting Guide

### 18.1 Build Failures

**"no matching manifest for linux/arm64 in the manifest list entries"**

_Cause:_ The base image does not support the target architecture. Not all images
published to Docker Hub include arm64 variants.

_Solution:_
- Check the base image's supported architectures: `docker buildx imagetools inspect <image>`
- Switch to a base image that supports both architectures
- For official images (node, python, alpine, ubuntu), multi-arch support is nearly universal
- For third-party images, check the image's README for architecture support

**"buildx failed with: ERROR: multiple platforms feature is not supported"**

_Cause:_ The `docker` driver is being used instead of `docker-container`.

_Solution:_ Ensure `setup-buildx-action` is configured with `driver: docker-container`.
The docker driver does not support multi-architecture builds.

**"failed to push: denied: resource not accessible"**

_Cause:_ The GITHUB_TOKEN does not have sufficient permissions.

_Solution:_
- Verify `permissions:` includes `packages: write`
- Check if the repository has a package already created at the target name
- For GHCR, the package is auto-created on first push if permissions are correct

### 18.2 Cache Misses

**"cache miss: no cache entry found for key"**

_Cause:_ The first run on a new branch, or the cache was evicted.

_Impact:_ Build takes longer (full rebuild) but still succeeds.

_Solution:_
- This is expected behavior for first runs
- Subsequent runs on the same branch will hit the cache
- For frequently evicted caches, consider adding `mode=max` to export more layers

**"cache import failed: specified credentials could not be used"**

_Cause:_ Registry authentication issue when using `type=registry` cache backend.

_Solution:_ Ensure the login action runs before the build action.

### 18.3 Cosign/Signing Issues

**"error: signing [IMAGE] at least one identity must be provided"**

_Cause:_ The OIDC token was not available to Cosign.

_Solution:_
- Verify `permissions:` includes `id-token: write`
- Check that Cosign is v2.0+ (keyless signing was GA in v2.0)
- Verify the `COSIGN_EXPERIMENTAL` environment variable is not set to `true`
  (it's required for v1.x but interferes with v2.x keyless signing)

**"error: verifying image: no matching signatures"**

_Cause:_ The image was pushed but not signed, or the signature is in a different
registry.

_Solution:_
- Confirm that `cosign sign` completed successfully
- Check the image repository for signature manifests (they appear as separate
  manifests in the registry UI)
- Verify you're using the correct digest

### 18.4 Trivy Issues

**"Trivy scan failed with exit code 1"**

_Cause:_ Vulnerabilities were found at the configured severity threshold.

This is EXPECTED behavior when `exit-code: 1` is set. The scan worked correctly —
it found issues. Check the SARIF output and CI logs for details.

To determine if it's a tool error vs. vulnerability finding:
- Check the step output for "CRITICAL" or "HIGH" severity listings
- If the output shows vulnerabilities, these are actionable items to fix
- If the output shows an error like "unable to initialize database," it's a tool issue

**"Trivy failed to download vulnerability database"**

_Cause:_ Network connectivity issue or Docker Hub rate limiting.

_Solution:_
- GitHub Actions runners have network access by default
- For rate limiting, Trivy automatically retries with backoff
- In air-gapped environments, configure a local Trivy mirror

### 18.5 Release Failures

**"Resource not accessible by integration" — release creation fails**

_Cause:_ The GITHUB_TOKEN does not have `contents: write` permission.

_Solution:_ Verify the workflow `permissions:` block includes `contents: write`.

**"Validation Error: Tag already exists" — tag_name conflict**

_Cause:_ A release with the same tag already exists.

_Solution:_
- Use unique tags for each build (semver or timestamp-based)
- The `workflow_dispatch` flow creates tags from the version, which should be unique
- For the `release` event trigger, the tag already exists (GitHub created it)

### 18.6 Cleanup Issues

**"delete failed: resource not accessible" — cleanup action fails**

_Cause:_ The GITHUB_TOKEN needs package deletion permissions which may not be granted
by default.

_Solution:_
- The `packages: write` permission is needed but may not be sufficient
- For GHCR package deletion, you may need a Personal Access Token with `delete:packages`
  scope
- Configure the PAT as a repository secret and pass it as the `token` input

---

## 19. Cost and Resource Optimization

### 19.1 Runner Time Analysis

Estimated runtime for each job in this workflow:

| Job | Est. Time | Parallel With | Cost Notes |
|---|---|---|---|
| docker-setup | ~30s | — | Baseline setup |
| docker-lint | ~20s | metadata | Fast, lightweight |
| metadata | ~15s | docker-lint | Fast, lightweight |
| build-push | ~3-8min | — | Most expensive (multi-arch build) |
| image-scan | ~2-3min | sbom-attest | First run downloads DB |
| sbom-attest | ~2-3min | image-scan | SBOM gen + Cosign |
| verify-image | ~1min | — | Pull + verify |
| release | ~30s | — | API call |
| cleanup | ~15s | — | API call |

**Total wall-clock time:** ~8-15 minutes (depending on build complexity and cache hits)

**Total runner minutes:** ~10-18 minutes (due to parallel execution)

### 19.2 Cache Cost Savings

Without caching (`--no-cache`), a typical multi-arch build takes 8-15 minutes.
With GHA cache and a 50%+ hit rate, build time drops to 2-5 minutes.

**Cost calculation (GitHub-hosted runners):**
- Linux runner: $0.008/min
- Without cache: 12 min avg → $0.096/run
- With cache: 4 min avg → $0.032/run
- Savings: ~67% per run
- At 50 runs/day: ~$3.20/day savings

### 19.3 Storage Management

GHCR storage limits:
- Free tier: 500 MB for private repos, unlimited for public
- Paid plan: Included in minutes
- Cleanup (job 9) is essential for staying within limits on private repos

Strategies for managing GHCR storage:
1. Delete untagged versions (this workflow)
2. Set a package-level retention policy (GitHub UI > Packages > Settings)
3. Use OCI index with shared layers (multi-arch images share base layers)
4. Keep only the last N tagged versions

---

## 20. Extending This Workflow

### 20.1 Adding More Platforms

To add ARM v7 (32-bit, for Raspberry Pi) to the build matrix:

1. Update the `platforms` input default:
```yaml
platforms:
  default: 'linux/amd64,linux/arm64,linux/arm/v7'
```

2. Verify the QEMU setup includes arm emulation:
```yaml
- name: Set up QEMU
  uses: docker/setup-qemu-action@v3
  with:
    platforms: arm64,arm
```

3. Verify the base image supports arm/v7:
```bash
docker buildx imagetools inspect node:22-slim | grep arm
```

### 20.2 Adding Image Promotion

To add an image promotion job (e.g., promote `edge` → `stable`):

```yaml
promote:
  needs: verify-image
  runs-on: ubuntu-latest
  if: github.ref == 'refs/heads/main'
  steps:
    - uses: docker/login-action@v3
      with:
        registry: ${{ env.REGISTRY }}
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}

    - name: Promote image to stable
      run: |
        docker buildx imagetools create \
          --tag ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:stable \
          ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }}
```

### 20.3 Adding Deployment

To deploy the verified image to a Kubernetes cluster:

```yaml
deploy:
  needs: verify-image
  runs-on: ubuntu-latest
  if: github.ref == 'refs/heads/main'
  environment: production
  steps:
    - uses: azure/setup-kubectl@v4

    - name: Update Kubernetes deployment
      run: |
        kubectl set image deployment/myapp \
          myapp=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build-push.outputs.digest }} \
          --record
```

### 20.4 Adding Notification

To send a Slack/DingTalk/Feishu notification:

```yaml
notify:
  needs: [verify-image, release, cleanup]
  runs-on: ubuntu-latest
  if: always()
  steps:
    - uses: slackapi/slack-github-action@v2
      with:
        webhook: ${{ secrets.SLACK_WEBHOOK }}
        webhook-type: incoming-webhook
        payload: |
          {
            "text": "Docker build complete: ${{ needs.build-push.outputs.digest }}"
          }
```

---

## 21. Workflow DAG Reference

### Complete Job Dependency Graph

```
                           ┌─────────────────┐
                           │   docker-setup   │
                           └────────┬────────┘
                                    │
                    ┌───────────────┼──────────────────┐
                    ▼               ▼                   │
             ┌──────────┐   ┌──────────┐               │
             │docker-lint│   │ metadata │               │
             └─────┬─────┘   └─────┬────┘               │
                   │               │                    │
                   └───────┬───────┘                    │
                           ▼                            │
                    ┌──────────────┐                    │
                    │  build-push  │                    │
                    └──────┬───────┘                    │
                           │                            │
               ┌───────────┴───────────┐                │
               ▼                       ▼                │
        ┌──────────┐           ┌────────────┐          │
        │image-scan│           │sbom-attest │          │
        └─────┬────┘           └──────┬─────┘          │
              │                       │                │
              └───────────┬───────────┘                │
                          ▼                            │
                   ┌──────────────┐                    │
                   │ verify-image │                    │
                   └──────┬───────┘                    │
                          │                            │
                          ▼                            │
                   ┌──────────────┐                    │
                   │   release    │  (branch condition)│
                   └──────┬───────┘                    │
                          │                            │
                          ▼                            │
                   ┌──────────────┐                    │
                   │   cleanup    │  (branch condition)│
                   └──────────────┘                    │
```

### Condition Matrix

| Job | main branch | dev branch | Feature branch | Release event |
|---|---|---|---|---|
| docker-setup | YES | YES | YES | YES |
| docker-lint | YES | YES | YES | YES |
| metadata | YES | YES | YES | YES |
| build-push | YES | YES | YES | YES |
| image-scan | YES (skip-scan?) | YES (skip-scan?) | YES (skip-scan?) | YES (skip-scan?) |
| sbom-attest | YES | YES | YES | YES |
| verify-image | YES | YES | YES | YES |
| release | YES | NO | NO | YES (attach) |
| cleanup | YES | NO | NO | NO |

---

## 22. Script and Command Reference

### Useful Docker Commands

```bash
# List multi-arch platforms for an image
docker buildx imagetools inspect node:22-slim

# Pull specific architecture
docker pull --platform linux/arm64 node:22-slim

# Inspect an image's layers
docker history ghcr.io/owner/repo@sha256:digest

# View SBOM attestation in image
docker buildx imagetools inspect ghcr.io/owner/repo@sha256:digest --format '{{ json .Attestations }}'

# Export SBOM from image
docker buildx imagetools inspect ghcr.io/owner/repo@sha256:digest --format '{{ range .Manifests }}{{ if eq .Annotations "sbom" }}{{ .Digest }}{{ end }}{{ end }}'

# Verify Cosign signature manually
cosign verify ghcr.io/owner/repo@sha256:digest \
  --certificate-identity-regexp "https://github.com/owner/repo/.github/workflows/.*" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com"

# Search Rekor for an image's signature
rekor-cli search --artifact sha256:digest

# Delete old images from GHCR manually
gh api --method DELETE "/orgs/owner/packages/container/repo-name/versions/version-id"
```

### Useful `gh` CLI Commands

```bash
# Trigger workflow manually
gh workflow run docker-full-lifecycle.yml \
  --field platforms="linux/amd64,linux/arm64" \
  --ref main

# List workflow runs
gh run list --workflow docker-full-lifecycle.yml

# View run logs
gh run view <run-id> --log

# Download artifacts from a run
gh run download <run-id> -n sbom-and-attestation

# Check package versions in GHCR
gh api /orgs/owner/packages/container/repo-name/versions --jq '.[].metadata.container.tags'
```

---

## End of Document

---

## 23. YAML Syntax Deep Dive

### 23.1 YAML Anchors and Aliases (for DRY workflows)

GitHub Actions supports YAML anchors (`&`) and aliases (`*`) to reduce repetition:

```yaml
# Define reusable blocks
.base-setup: &base-setup
  - uses: actions/checkout@v4
  - uses: docker/login-action@v3
    with:
      registry: ghcr.io
      username: ${{ github.actor }}
      password: ${{ secrets.GITHUB_TOKEN }}

jobs:
  job-a:
    steps:
      - *base-setup                  # Reuse the anchor
      - run: echo "doing something"

  job-b:
    steps:
      - *base-setup                  # Reuse again
      - run: echo "doing something else"
```

While this workflow doesn't use anchors (they can be confusing in debugging), they are
a useful technique for reducing boilerplate in large workflows with many jobs.

### 23.2 Matrix Strategies

The matrix strategy creates multiple job variants from a single job definition. While
this workflow uses a single-platform strategy (no matrix), here's how a matrix would
look for multi-platform builds:

```yaml
build-matrix:
  strategy:
    matrix:
      platform:
        - linux/amd64
        - linux/arm64
        - linux/arm/v7
    # Don't cancel all runners when one fails
    fail-fast: false
    # Use the max parallel limit
    max-parallel: 3
  steps:
    - uses: docker/build-push-action@v6
      with:
        platforms: ${{ matrix.platform }}
        tags: ghcr.io/owner/repo:${{ matrix.platform }}
```

However, using a single build-push with multiple `platforms:` is preferred because:
- BuildKit builds all platforms in parallel internally
- A single multi-arch manifest list is created
- The push creates one OCI index referencing all platforms
- Matrix builds create separate image tags per platform, not a manifest list

### 23.3 Concurrency Groups

For production use, add a `concurrency` block to prevent redundant runs:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

This cancels in-progress runs when a new commit is pushed to the same branch, saving
CI minutes. Without this, every commit triggers a new run while the previous one
completes — wasting resources on outdated builds.

### 23.4 Timeouts

Set job-level timeouts to prevent runaway builds:

```yaml
build-push:
  timeout-minutes: 30
```

Default timeout is 360 minutes (6 hours) for GitHub-hosted runners. For CI efficiency,
set timeouts that reflect realistic expectations. A multi-arch Docker build rarely needs
more than 15-20 minutes with caching.

### 23.5 Environment URLs

Link the workflow run UI to the deployed release:

```yaml
release:
  steps:
    - name: Create Release
      uses: softprops/action-gh-release@v2
      # ...
    - name: Set deploy URL
      run: |
        echo "deploy_url=https://github.com/${{ github.repository }}/releases/tag/v${{ needs.metadata.outputs.version }}" >> "$GITHUB_ENV"
```

The deploy URL appears in the workflow run summary as a clickable link.

---

## 24. Workflow Outputs Summary

### Job Outputs Table

| Job | Output | Type | Description | Consumed By |
|---|---|---|---|---|
| docker-setup | builder-name | string | Buildx builder instance name | Diagnostic only |
| metadata | tags | string (comma-sep) | Docker image tags | build-push |
| metadata | labels | string (comma-sep) | OCI image labels | build-push |
| metadata | json | string (JSON) | Full metadata JSON | Any |
| metadata | version | string | Detected version | build-push, release |
| build-push | digest | string (sha256:) | Image manifest digest | image-scan, sbom-attest, verify-image, release |
| build-push | tags | string | Built tags | release |
| build-push | image-with-digest | string | Full immutable reference | Diagnostic |

---

## 25. Environment Variables Reference

### Workflow-Level Variables

| Variable | Value | Description | Used In |
|---|---|---|---|
| `REGISTRY` | `ghcr.io` | Container registry hostname | login, build, push, verify |
| `IMAGE_NAME` | `${{ github.repository }}` | Image name (owner/repo) | All image references |
| `TRIVY_SEVERITY` | `CRITICAL,HIGH` | Vulnerability severity threshold | image-scan |

### Secrets Used

| Secret | Source | Description | Used In |
|---|---|---|---|
| `GITHUB_TOKEN` | Auto-generated | Repository-scoped token | login, release, cleanup, attest |

---

## Quick Reference: Files Created

| File | Lines | Purpose |
|---|---|---|
| `.github/workflows/docker-full-lifecycle.yml` | ~550 | The workflow definition with 9 jobs |
| `.github/workflow-lab/docs/workflow-2-docker-lifecycle.md` | ~3000+ | This comprehensive documentation |

---

## End of Document
