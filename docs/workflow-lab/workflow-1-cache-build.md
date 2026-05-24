# Workflow 1: Advanced Cache & Build Acceleration — Complete Guide

> **Audience:** Developers new to GitHub Actions who want to understand production-grade caching, matrix builds, and CI/CD acceleration.
>
> **File:** `.github/workflows/advanced-cache-build.yml`
>
> **Concepts covered:** Triggers, permissions, concurrency, `hashFiles()`, `matrix` strategy, `actions/cache` (save/restore), artifacts, Docker layer caching, conditional execution, expression syntax, and context objects.

---

## Table of Contents

1. [File Overview and Top-Level Structure](#1-file-overview-and-top-level-structure)
2. [Trigger Syntax (on:)](#2-trigger-syntax-on)
3. [Permissions Block](#3-permissions-block)
4. [Concurrency Groups](#4-concurrency-groups)
5. [Environment Defaults (env:)](#5-environment-defaults-env)
6. [Job 1: cache-calc — Centralized Cache Key Computation](#6-job-1-cache-calc)
7. [Job 2: deps-install — Matrix Dependency Installation with Caching](#7-job-2-deps-install)
8. [Job 3: lint — Fast-Feedback Code Quality](#8-job-3-lint)
9. [Job 4: docker-prepare — Docker Layer Cache Pre-build](#9-job-4-docker-prepare)
10. [Job 5: build — Matrix Build with Output Artifacts](#10-job-5-build)
11. [Job 6: test-unit — Matrix Test Sharding](#11-job-6-test-unit)
12. [Job 7: test-integration — Docker Compose Integration Tests](#12-job-7-test-integration)
13. [Job 8: cache-warm — Main Branch Cache Priming](#13-job-8-cache-warm)
14. [Expression Syntax and Context Objects](#14-expression-syntax-and-context-objects)
15. [Key Patterns Summary](#15-key-patterns-summary)

---

## 1. File Overview and Top-Level Structure

### YAML

```yaml
# =============================================================================
# Advanced Cache & Build Acceleration
# =============================================================================
# A production-grade GitHub Actions workflow demonstrating multi-layer caching,
# matrix builds, artifact pass-through, Docker layer caching, and cache warming.
#
# Key concepts demonstrated:
#   - Centralized cache key computation (cache-calc job)
#   - Matrix strategies for Node versions, OS variants, and test sharding
#   - Explicit cache restore/save vs. automatic post-action caching
#   - Artifact upload/download for pass-through between jobs
#   - Docker layer caching with BuildKit cache backend
#   - concurrency groups to cancel redundant runs
#   - Conditional execution (main-branch-only cache warming)
# =============================================================================

name: Advanced Cache & Build Acceleration
```

### Line-by-Line Explanation

| Lines | Element | Explanation |
|-------|---------|-------------|
| 1-14 | `#` comments | YAML comments. Everything after `#` to end of line is ignored. These are block-level documentation comments explaining the file's purpose. |
| 16 | `name:` | The workflow name appears in the GitHub Actions UI (top-left of each workflow run). Choose a descriptive name since multiple workflows may exist. |

### Action Capability: Commenting in YAML

YAML supports single-line comments with `#`. There is no multi-line comment syntax in standard YAML. Use `#` at the start of each comment line. Inline comments are also valid:

```yaml
name: Build  # inline comment
```

### Why This Approach

Block comments at the top of the file serve as:
- **Quick reference** for developers reading the file
- **Design documentation** that travels with the code
- **Onboarding aid** for new team members learning GitHub Actions patterns

---

## 2. Trigger Syntax (on:)

### YAML

```yaml
# ---------------------------------------------------------------------------
# Triggers
# ---------------------------------------------------------------------------
# push:       CI on every commit to main or dev branches
# pull_request: CI when a PR targets dev (catches issues before merge)
# workflow_dispatch: manual trigger via GitHub UI or API for testing
# ---------------------------------------------------------------------------
on:
  push:
    branches: [main, dev]
  pull_request:
    branches: [dev]
  workflow_dispatch:
```

### Line-by-Line Explanation

| Line | Element | Explanation |
|------|---------|-------------|
| 1 | `on:` | The `on` (or `trigger`) keyword defines which events cause this workflow to run. It's the entry point for workflow execution. |
| 2 | `push:` | Run the workflow on `git push` events. |
| 3 | `branches: [main, dev]` | Only trigger for pushes to `main` or `dev` branches. The YAML array syntax `[main, dev]` is equivalent to the block form: `branches:\n  - main\n  - dev`. |
| 4 | `pull_request:` | Run the workflow on pull request events (opened, synchronize, reopened by default). |
| 5 | `branches: [dev]` | Only trigger PR events when the PR targets the `dev` branch. PRs targeting `main` directly won't trigger this workflow. |
| 6 | `workflow_dispatch:` | Allows manual triggering from the GitHub Actions UI, the `gh workflow run` CLI command, or the REST API. No additional configuration needed. |

### Action Capability: Event Triggers

GitHub Actions supports many event types. The most common:

| Event | When It Fires | Common Use |
|-------|---------------|------------|
| `push` | A commit is pushed | CI for every commit |
| `pull_request` | PR is opened/updated | Pre-merge validation |
| `workflow_dispatch` | Manual trigger | Ad-hoc runs, debugging |
| `schedule` | Cron schedule | Nightly builds, maintenance |
| `release` | Release published | Deploy workflows |
| `issue_comment` | Comment on issue/PR | Chatops, /trigger commands |

**Branch filtering** (`branches:`) can be literal names or glob patterns:
- `main` — exact match
- `dev` — exact match
- `release/**` — any branch starting with `release/`
- `!alpha` — exclude `alpha`

**Important:** `push` branches filter WHICH branches trigger on push. `pull_request` branches filter which TARGET branches trigger the PR check. They serve different purposes.

### Why This Approach

- **`push` on main + dev:** Every commit gets tested immediately. No one pushes broken code without knowing.
- **`pull_request` on dev:** PRs targeting dev are validated before merge. This catches issues in review before they reach main.
- **`workflow_dispatch`:** Essential for testing workflow changes. Without this, you'd need to push a commit every time you want to test a modification.
- **Omitting PR on main:** Changes reach main only through PRs merged from dev, so the dev PR check covers it.

---

## 3. Permissions Block

### YAML

```yaml
# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------
# contents: read     — needed for checkout
# checks: write      — allows dorny/test-reporter to create check runs
# pull-requests: write — allows test-reporter to write PR comments
# ---------------------------------------------------------------------------
permissions:
  contents: read
  checks: write
  pull-requests: write
```

### Line-by-Line Explanation

| Line | Element | Explanation |
|------|---------|-------------|
| 1 | `permissions:` | Defines the GITHUB_TOKEN permissions for this workflow. GitHub Actions auto-generates a token scoped to the repository. |
| 2 | `contents: read` | Read access to repository contents. Required for `actions/checkout`. Without this, checkout fails. |
| 3 | `checks: write` | Write access to check runs API. Used by `dorny/test-reporter` to create check run entries visible in the GitHub UI. |
| 4 | `pull-requests: write` | Write access to pull requests. Used by `dorny/test-reporter` to comment on PRs with test results. |

### Action Capability: GITHUB_TOKEN and Permissions

Every workflow run gets a `secrets.GITHUB_TOKEN` with configurable scope. The fine-grained permissions model (GA in late 2023) replaced the earlier broad `write-all` default.

**Available permissions:**

| Permission | What it grants |
|------------|---------------|
| `actions` | Read/write actions (artifacts, cache, workflow runs) |
| `checks` | Read/write check runs and suites |
| `contents` | Read/write repository contents (commits, releases, tags) |
| `deployments` | Read/write deployments |
| `id-token` | Read/write OIDC token (for cloud provider auth) |
| `issues` | Read/write issues |
| `pull-requests` | Read/write pull requests |
| `packages` | Read/write GitHub Packages |

**Security best practice:** Grant only the minimum permissions needed. The old default of `write-all` meant any compromised workflow could push code. Explicit `permissions:` blocks are now required for new repositories.

### Why This Approach

- `contents: read` is the minimum for checkout.
- `checks: write` enables rich test reporting natively in GitHub (no external service needed).
- `pull-requests: write` allows automated PR comments with test summaries.
- No additional permissions means no token abuse surface.

---

## 4. Concurrency Groups

### YAML

```yaml
# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------
# Groups runs by workflow name + branch ref so that if a new commit is pushed
# before the previous run finishes, the in-progress run is cancelled.
# This saves CI minutes on fast-iteration branches.
# ---------------------------------------------------------------------------
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

### Line-by-Line Explanation

| Line | Element | Explanation |
|------|---------|-------------|
| 1 | `concurrency:` | Defines a concurrency group — a logical queue for workflow runs. |
| 2 | `group:` | The group identifier. Only one run per group executes at a time. |
| 3 | `${{ github.workflow }}` | Expression: expands to the workflow name ("Advanced Cache & Build Acceleration"). |
| 4 | `${{ github.ref }}` | Expression: expands to the branch or tag ref (e.g., `refs/heads/dev`). |
| 5 | `cancel-in-progress: true` | When a new run joins the group, cancel any in-progress run in the same group. |

### How Concurrency Groups Work

```
Scenario:
  Push to dev at t=0  → Run #1 starts
  Push to dev at t=30 → Run #2 is queued (same group: "Build-refs/heads/dev")
                        → Run #1 is cancelled via API
                        → Run #2 starts immediately

Scenario 2 (different branches):
  Push to dev  → Run #1 starts (group: "Build-refs/heads/dev")
  Push to main → Run #2 starts (group: "Build-refs/heads/main")
  Both run in parallel — different group keys.
```

### Expression Syntax: `${{ }}`

The `${{ }}` delimiters mark GitHub Actions expressions. Everything inside is evaluated by the Actions expression parser before the step runs. This is distinct from shell variable expansion (`$VAR` or `${VAR}`).

**Key properties:**
- Expressions are evaluated server-side, before the runner executes
- They can appear in ANY field of a workflow (not just `run:`)
- They have access to context objects: `github`, `env`, `runner`, `matrix`, `needs`, `secrets`, `inputs`, `steps`

### Why This Approach

- **Cancel-in-progress saves CI minutes.** If you push three commits in quick succession, only the last one runs to completion.
- **Group key uses `github.ref`** so different branches don't cancel each other. Main and dev run independently.
- **Without this,** every push enqueues a new run and all of them execute, burning CI minutes on intermediate states that don't matter.

---

## 5. Environment Defaults (env:)

### YAML

```yaml
# ---------------------------------------------------------------------------
# Environment defaults
# ---------------------------------------------------------------------------
env:
  NODE_VERSION: 20       # default Node.js version for non-matrix jobs
  NODE_LTS: 22           # latest LTS for docker-prepare and cache-warm
```

### Line-by-Line Explanation

| Line | Element | Explanation |
|------|---------|-------------|
| 1 | `env:` | Defines environment variables available to ALL jobs and steps in the workflow. |
| 2 | `NODE_VERSION: 20` | Custom env var. Accessed via `${{ env.NODE_VERSION }}` in expressions or `$NODE_VERSION` in shell steps. |
| 3 | `NODE_LTS: 22` | Another custom env var. Note: this is defined but only used as a reference in documentation comments. |

### Action Capability: Environment Variable Scopes

Environment variables in GitHub Actions have three levels:

| Scope | Defined in | Available to |
|-------|------------|-------------|
| **Workflow** | `env:` at top level | All jobs and steps |
| **Job** | `jobs.<job_id>.env:` | All steps in that job |
| **Step** | `steps[*].env:` or `steps[*].with.env` | Only that specific step |
| **Runtime** | `echo "NAME=value" >> $GITHUB_ENV` | Subsequent steps in the same job |

Access methods:
- **Expressions:** `${{ env.NODE_VERSION }}` (evaluated server-side)
- **Shell:** `$NODE_VERSION` or `${NODE_VERSION}` (evaluated on the runner)

### Why This Approach

- Single source of truth for the default Node version. Change one line, and all non-matrix jobs pick it up.
- Using env vars instead of hardcoding numbers makes the workflow more maintainable and self-documenting.

---

## 6. Job 1: cache-calc

### YAML

```yaml
# =============================================================================
# Job 1: cache-calc — Centralized Cache Key Computation
# =============================================================================
# Purpose: Single source of truth for ALL cache keys in the pipeline.
# Every downstream job reads key prefixes from this job's outputs, ensuring
# consistent key construction and eliminating key-drift bugs.
#
# Why a dedicated job:
#   - Avoids every job running its own hashFiles() with different patterns
#   - Makes cache invalidation logic auditable in one place
#   - Outputs are strongly typed (job outputs in needs.<id>.outputs.<name>)
# =============================================================================
cache-calc:
  runs-on: ubuntu-latest
  # These outputs are consumed by downstream jobs via ${{ needs.cache-calc.outputs.* }}
  outputs:
    dep-key:     ${{ steps.compute.outputs.dep-key }}
    build-key:   ${{ steps.compute.outputs.build-key }}
    docker-key:  ${{ steps.compute.outputs.docker-key }}
    test-key:    ${{ steps.compute.outputs.test-key }}
  steps:
    # Checkout is required for hashFiles() to operate on the repository content
    - uses: actions/checkout@v4

    # Each key uses hashFiles() to fingerprint the relevant inputs:
    #   - dep-key:      lockfile is the canonical source of dependency truth
    #   - build-key:    source files + tsconfig + dep-key (chained invalidation)
    #   - docker-key:   Dockerfile + .dockerignore + dep-key (deps chain)
    #   - test-key:     test source files
    #
    # Key chaining: build-key includes dep-key via the package-lock.json hash.
    # When deps change, both dep AND build caches invalidate automatically.
    - id: compute
      name: Compute all cache keys
      run: |
        echo "dep-key=npm-cache-${{ hashFiles('package-lock.json') }}-${{ runner.os }}" >> "$GITHUB_OUTPUT"
        echo "build-key=build-${{ hashFiles('src/**/*.ts', 'tsconfig.json', 'web/tsconfig.json') }}-${{ hashFiles('package-lock.json') }}" >> "$GITHUB_OUTPUT"
        echo "docker-key=docker-${{ hashFiles('Dockerfile', '.dockerignore') }}-${{ hashFiles('package-lock.json') }}" >> "$GITHUB_OUTPUT"
        echo "test-key=test-${{ hashFiles('src/**/*.test.ts', 'tests/**/*.test.ts') }}" >> "$GITHUB_OUTPUT"
```

### Line-by-Line Explanation

#### Job Definition

| Line | Element | Explanation |
|------|---------|-------------|
| 1-23 | `#` comments | Documentation header explaining the job's purpose and design rationale. |
| 24 | `cache-calc:` | The job ID. Must be unique within the workflow. Used as the identifier in `needs:` and `needs.<id>.outputs.*`. |
| 25 | `runs-on: ubuntu-latest` | Specifies the runner environment. `ubuntu-latest` is the standard Linux runner (currently Ubuntu 22.04 or 24.04). |
| 26-27 | `#` comment | Reminder that these outputs are consumed elsewhere. |
| 28-31 | `outputs:` | Job-level output declarations. Each maps a name to an expression. Downstream jobs access these via `${{ needs.cache-calc.outputs.dep-key }}`. |
| 28 | `dep-key:` | Output name. The value is the expression `${{ steps.compute.outputs.dep-key }}`, which reads the `dep-key` output from the step with `id: compute`. |
| 29 | `build-key:` | Same pattern: reads `steps.compute.outputs.build-key`. |
| 30 | `docker-key:` | Same pattern: reads `steps.compute.outputs.docker-key`. |
| 31 | `test-key:` | Same pattern: reads `steps.compute.outputs.test-key`. |

#### Steps

| Line | Element | Explanation |
|------|---------|-------------|
| 33-34 | `#` comment + step | `uses: actions/checkout@v4` — the official checkout action. Clones the repository into the runner's workspace. **Required** for `hashFiles()` to find files. |
| 35-46 | `#` comments | Documentation explaining the key computation strategy. |
| 47 | `- id: compute` | Sets the step ID to `compute`. This ID is used by `steps.compute.outputs.*` in the job-level `outputs:` block. |
| 48 | `name: Compute all cache keys` | Human-readable step name shown in the GitHub Actions log UI. |
| 49 | `run: \|` | The pipe `\|` starts a multi-line YAML string (literal block scalar). Each line is preserved as-is with newlines. |
| 50 | `echo "...dep-key..." >> "$GITHUB_OUTPUT"` | Writes a step output to the `GITHUB_OUTPUT` file. Format: `name=value`. The `$GITHUB_OUTPUT` file is a workflow command mechanism — any line written to this file becomes a step output accessible via `steps.<id>.outputs.<name>`. |
| 51 | `${{ hashFiles('package-lock.json') }}` | The `hashFiles()` function computes a SHA-256 hash of the matched files. With a single file argument, it returns `hash(file)`. |
| 52 | `${{ runner.os }}` | Expands to the operating system of the runner (e.g., `Linux`). |
| 53 | `${{ hashFiles('src/**/*.ts', 'tsconfig.json', 'web/tsconfig.json') }}` | `hashFiles()` with multiple glob patterns computes a single combined hash of all matching files. The `**/*.ts` glob matches TypeScript files recursively in `src/`. |
| 54 | `${{ hashFiles('Dockerfile', '.dockerignore') }}` | Hashes the Docker configuration files. |
| 55 | `${{ hashFiles('src/**/*.test.ts', 'tests/**/*.test.ts') }}` | Hashes test files specifically. |

### Action Capability: Job Outputs (`outputs:`)

**Syntax:**
```yaml
jobs:
  <job-id>:
    outputs:
      <output-name>: <expression>
```

**How outputs flow:**
1. A step within the job writes to `$GITHUB_OUTPUT`:
   ```bash
   echo "my-key=some-value" >> "$GITHUB_OUTPUT"
   ```
2. The step's output is accessed as `${{ steps.<step-id>.outputs.my-key }}`.
3. The job's `outputs:` block maps this to a job-level output:
   ```yaml
   outputs:
     my-key: ${{ steps.my-step.outputs.my-key }}
   ```
4. Downstream jobs access it as `${{ needs.<job-id>.outputs.my-key }}`.

**Important constraints:**
- Outputs are strings only (no arrays or objects)
- Outputs from matrix jobs must reference the specific matrix variant
- Output size is limited (approximately 1 MB total for all outputs)

### Action Capability: `hashFiles()` Function

**Syntax:**
```
hashFiles('<glob-pattern>', '<glob-pattern>', ...)
```

**Behavior:**
- Accepts one or more glob patterns
- Returns a single SHA-256 hash of ALL files matched by ALL patterns
- Files are sorted alphabetically before hashing, so the order of patterns doesn't matter
- Returns an empty string if no files match
- **Only works after `actions/checkout`** — the function reads from the workspace

**Glob patterns:**
- `*` — matches any characters except `/`
- `**` — matches any number of directories (recursive)
- `?` — matches a single character
- `[abc]` — character range
- `!` prefix — negate the pattern (exclude matching files)

**Examples:**
```yaml
# Single file
hashFiles('package-lock.json')

# Multiple patterns combined
hashFiles('src/**/*.ts', 'src/**/*.tsx', 'tsconfig.json')

# Exclude test files from build hash
hashFiles('src/**/*.ts', '!src/**/*.test.ts')

# No match → empty string (cache key would be constant!)
hashFiles('nonexistent.file')
```

### Why This Approach

**Centralized key computation** solves a real problem: when every job computes its own cache key, subtle differences in glob patterns cause cache misses. For example, one job uses `hashFiles('src/**/*.ts')` while another uses `hashFiles('src/**/*.ts', '!src/**/*.test.ts')`. These produce different hashes even when the same files changed.

**Key chaining** ensures that cache invalidation propagates correctly:
- `build-key` includes the `package-lock.json` hash. When deps change, the build key changes too.
- This prevents using a stale build output with newer dependencies.
- No need for manual invalidation logic.

---

## 7. Job 2: deps-install

### YAML

```yaml
# =============================================================================
# Job 2: deps-install — Install npm Dependencies with Caching (Matrix)
# =============================================================================
# Purpose: Install npm dependencies across 3 Node versions. Each combination
# is cached independently and the resulting node_modules/ is uploaded as an
# artifact for downstream jobs to consume.
#
# Cache strategy:
#   1. Attempt exact restore using the full dep-key (including node version)
#   2. On miss, try restore-keys (prefix match — reusable across node versions)
#   3. npm ci --prefer-offline (uses global npm cache as second fallback)
#   4. Post-job: actions/cache auto-saves if key was missing (post-action)
#
# Why matrix node versions:
#   - Ensures compatibility across all supported Node.js versions
#   - Downstream build + test jobs use the same matrix for consistency
# =============================================================================
deps-install:
  needs: cache-calc
  runs-on: ubuntu-latest
  strategy:
    matrix:
      node: [18, 20, 22]   # Active LTS releases per Node.js release schedule
  steps:
    - uses: actions/checkout@v4

    # setup-node with cache: npm manages the GLOBAL npm cache (~/.npm/)
    # This speeds up npm ci even if our node_modules cache misses
    - uses: actions/setup-node@v4
      with:
        node-version: ${{ matrix.node }}
        cache: npm

    # Explicit cache restore for node_modules/
    # Using actions/cache/restore@v4 (the restore-only sub-action) gives us
    # exact control — we only restore here and let the post-job save handle
    # persistence after npm ci modifies node_modules.
    - name: Restore node_modules cache
      id: deps-cache-restore
      uses: actions/cache/restore@v4
      with:
        path: node_modules
        # Full key includes node version — different Node builds produce
        # different node_modules (native addons like better-sqlite3)
        key: ${{ needs.cache-calc.outputs.dep-key }}-${{ matrix.node }}
        # Fallback restore keys (prefix-based partial match):
        #   1. Same OS + lockfile, any node version
        #   2. Same OS only, any lockfile
        # GitHub Actions returns the LATEST written cache matching the prefix
        restore-keys: |
          ${{ needs.cache-calc.outputs.dep-key }}-
          npm-cache-

    # --prefer-offline: use global npm cache first, only fetch missing packages
    - name: Install dependencies
      run: npm ci --prefer-offline

    # Upload the full node_modules/ as a build artifact
    # Downstream jobs download this instead of re-running npm ci
    # Retention: 1 day (short — artifacts are only needed within a single run)
    - name: Upload node_modules artifact
      uses: actions/upload-artifact@v4
      with:
        name: node_modules-${{ matrix.node }}
        path: node_modules/
        retention-days: 1
```

### Line-by-Line Explanation

#### Job Definition

| Line | Element | Explanation |
|------|---------|-------------|
| 1-22 | `#` comments | Documentation header. |
| 23 | `deps-install:` | Job ID. Uses a hyphenated name (kebab-case), which is the most common convention for GitHub Actions job IDs. |
| 24 | `needs: cache-calc` | Declares dependency on the `cache-calc` job. This job will NOT start until `cache-calc` completes successfully. If `cache-calc` fails, this job is skipped (unless `if: always()` is used). |
| 25 | `runs-on: ubuntu-latest` | All deps-install matrix jobs run on Ubuntu. |
| 26-28 | `strategy:` / `matrix:` | Defines the build matrix. The job runs once for each combination of values. |
| 27 | `node: [18, 20, 22]` | Three values → three parallel job instances. Each instance has `${{ matrix.node }}` set to one of these values. |
| 29-31 | Steps | Checkout and setup. |

#### Matrix Step

| Line | Element | Explanation |
|------|---------|-------------|
| 33 | `- uses: actions/setup-node@v4` | The official Node.js setup action. Downloads and caches the specified Node.js version. |
| 35 | `node-version: ${{ matrix.node }}` | `${{ matrix.node }}` expands to the current matrix value (18, 20, or 22). |
| 36 | `cache: npm` | **Critical feature:** tells setup-node to save/restore the global npm cache (`~/.npm/`). This speeds up `npm ci` by avoiding re-downloading packages from the registry. Unlike our node_modules cache, this is a package-level cache, not a `node_modules/` cache. |

#### Cache Restore Step

| Line | Element | Explanation |
|------|---------|-------------|
| 38-39 | `name:` + `id:` | Human-readable name and machine-readable ID. The `id:` is used to check `steps.deps-cache-restore.outputs.cache-hit` later. |
| 40 | `uses: actions/cache/restore@v4` | The restore-only sub-action from the `actions/cache` bundle. Version `v4` is the latest stable. |
| 42 | `path: node_modules` | The directory to restore from cache. Must match exactly what was cached. |
| 44 | `key: ${{ needs.cache-calc.outputs.dep-key }}-${{ matrix.node }}` | The primary cache key. Constructed from: `dep-key` from cache-calc (contains lockfile hash + OS) + node version. Example: `npm-cache-a1b2c3d4-Linux-20`. |
| 46-47 | `restore-keys: \|` + multi-line | Fallback keys for partial matches. The pipe `\|` creates a multi-line string. Each line is tried in order if the primary key misses. |
| 46 | `${{ needs.cache-calc.outputs.dep-key }}-` | First fallback: matches any cache whose key starts with this prefix. Since dep-key includes lockfile hash and OS but NOT node version, this matches any node version for the same lockfile+OS. |
| 47 | `npm-cache-` | Second fallback: matches ANY cache with the `npm-cache-` prefix. Catches the case where the lockfile changed but there's some prior cache. |

#### Install Step

| Line | Element | Explanation |
|------|---------|-------------|
| 50 | `run: npm ci --prefer-offline` | `npm ci` — clean install from lockfile (faster and more reproducible than `npm install`). `--prefer-offline` tells npm to use the global cache first, only fetching missing packages. If the node_modules restore hit, this step is fast (just verification); if the restore missed but the npm global cache hit, it avoids network fetches. |

#### Artifact Upload Step

| Line | Element | Explanation |
|------|---------|-------------|
| 52-57 | Upload step | Uploads the installed `node_modules/` as a build artifact. |
| 54 | `name: node_modules-${{ matrix.node }}` | Artifact name unique per node version. Example: `node_modules-20`. |
| 55 | `path: node_modules/` | Path to upload. The trailing `/` is optional but conventional. |
| 56 | `retention-days: 1` | **Key setting:** artifacts are deleted after 1 day. Build artifacts are only needed within the same workflow run, which typically takes minutes, not days. Short retention saves storage costs. |

### Action Capability: `actions/cache/restore@v4`

**Purpose:** Restore a previously cached directory by key.

**Key inputs:**

| Input | Required | Description |
|-------|----------|-------------|
| `path` | Yes | File/directory paths to restore (supports globs, multiple paths separated by newlines) |
| `key` | Yes | Exact cache key to look up |
| `restore-keys` | No | Ordered list of prefix keys for fallback matching |
| `fail-on-cache-miss` | No | If `true`, fail the step when no cache entry matches (default: `false`) |
| `lookup-only` | No | If `true`, check if cache exists without restoring (for pre-flight checks) |

**Key outputs:**

| Output | Description |
|--------|-------------|
| `cache-hit` | `"true"` if an exact match was found, `"false"` if only partial match or miss |
| `cache-primary-key` | The key that was provided |
| `cache-matched-key` | The actual key that was matched (may differ with restore-keys) |

**Cache matching logic:**

1. Try exact match with `key`. If found → `cache-hit: "true"`, restore immediately.
2. If no exact match, try each `restore-keys` in order. For each, find the MOST RECENTLY WRITTEN cache entry whose key STARTS WITH the prefix.
3. If any restore-key matches → `cache-hit: "false"` (important: not `"true"`), restore from partial match.
4. If no match at all → nothing is restored.

**The `cache-hit` distinction matters:**
- `"true"` → node_modules is exactly what `npm ci` would produce. Safe to skip `npm ci`.
- `"false"` → node_modules is from a different key. Should run `npm ci` to ensure correctness. However, the partial restore speeds up `npm ci` because most packages are already present.

### Action Capability: `actions/cache@v4` (Full Action)

The full `actions/cache@v4` action combines restore (pre-step) and save (post-step). When you use `actions/cache@v4` in a step, it:
1. Restores the cache at the start of the step (like `cache/restore`)
2. Registers a post-job hook that saves the cache AFTER the job completes (like `cache/save`)

**Why we use `cache/restore` instead of `cache`:** Separating restore and save gives us finer control. We restore explicitly, run `npm ci`, and let the automatic post-action save handle persistence. The post-action save only runs if the cache key was NEW (not on cache hit). This avoids unnecessary cache writes.

### Action Capability: `actions/upload-artifact@v4`

**Purpose:** Upload files from the runner to GitHub's artifact storage.

**Key inputs:**

| Input | Required | Description |
|-------|----------|-------------|
| `name` | Yes (default: `artifact`) | Artifact name for identification. Used by `download-artifact`. |
| `path` | Yes | File/directory paths to upload (supports globs, multiple paths) |
| `retention-days` | No | Days to keep the artifact (default: 90, max: depends on org settings) |
| `if-no-files-found` | No | What to do if no files match: `warn` (default), `error`, `ignore` |
| `compression-level` | No | Gzip compression level (0-9, default: 6) |

**Retention notes:**
- Default retention is 90 days (adjustable at org level)
- Set SHORT retention for intermediate artifacts (1-3 days)
- Long retention only for final release artifacts
- GitHub bills storage per month; short retention reduces costs

### Why This Approach

**Matrix for Node versions:** Ensures compatibility. Native modules (like `better-sqlite3`) may compile differently across Node versions.

**Separate cache per node version:** Two jobs with different `matrix.node` values produce different cache keys. Node 20's native addons don't work with Node 22's runtime. If we used a shared cache, we'd get runtime errors.

**Fallback `restore-keys`:**
- If the exact key `npm-cache-a1b2c-Linux-22` misses (e.g., first CI run for node 22), the fallback `npm-cache-a1b2c-Linux-` matches the cache from a previous node 20 run.
- This gives a useful partial restore even on the first run for a new node version.
- `npm ci` only needs to fetch packages that differ between node versions.

**Artifact instead of cache for downstream jobs:**
- Artifacts are faster to download than cache restores (within the same workflow run)
- Artifacts don't have the cache size limits (10GB vs ~2GB per cache entry)
- Artifacts are isolated to the specific workflow run — no cross-run contamination
- Cache is for COLD START (first run on a branch), artifacts are for SUBSEQUENT JOBS within the same run

---

## 8. Job 3: lint

### YAML

```yaml
# =============================================================================
# Job 3: lint — Lint + TypeScript Type Check
# =============================================================================
# Purpose: Fastest-feedback job. Lint and typecheck run as soon as dependencies
# are installed, without waiting for the full build pipeline.
#
# This job intentionally uses a SINGLE Node version (20 from env):
#   - Linting and type checking are toolchain concerns, not runtime concerns
#   - Running across 3 nodes would waste CI minutes with no additional signal
# =============================================================================
lint:
  needs: deps-install
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - uses: actions/setup-node@v4
      with:
        node-version: ${{ env.NODE_VERSION }}

    # Download node_modules from the deps-install matrix for node 20
    # This avoids re-running npm ci — saves ~30-60s per run
    - name: Download node_modules
      uses: actions/download-artifact@v4
      with:
        name: node_modules-${{ env.NODE_VERSION }}
        path: node_modules

    - name: Run linter
      run: npm run lint

    - name: TypeScript type check
      run: npx tsc --noEmit
```

### Line-by-Line Explanation

| Line | Element | Explanation |
|------|---------|-------------|
| 1-14 | `#` comments | Documentation. Key point: lint is single-node for speed. |
| 15 | `lint:` | Job ID. |
| 16 | `needs: deps-install` | Depends on `deps-install`. Subtle point: `deps-install` is a matrix job. When you put a matrix job in `needs:`, you wait for ALL matrix variants to complete. However, we only download the node 20 variant. |
| 17 | `runs-on: ubuntu-latest` | Linux runner. |
| 19-20 | Checkout | Standard checkout. |
| 22-25 | Setup Node | Uses `${{ env.NODE_VERSION }}` (20). No `cache: npm` needed because we're not running `npm ci`. |
| 27-32 | Download `node_modules` | Downloads the pre-installed `node_modules` artifact from `deps-install` for node 20. |
| 29 | `name: node_modules-${{ env.NODE_VERSION }}` | Matches the artifact name from `deps-install`. This must match EXACTLY — artifact names are case-sensitive. |
| 30 | `path: node_modules` | Where to place the downloaded artifact in the workspace. |
| 33-34 | `npm run lint` | Runs the linter (ESLint). `package.json` script: `eslint src/ tests/`. |
| 35-36 | `npx tsc --noEmit` | TypeScript type check without emitting output files. `--noEmit` is critical — it tells `tsc` to only type-check, not compile. This is faster than a full compilation. |

### Action Capability: `actions/download-artifact@v4`

**Purpose:** Download artifacts previously uploaded in the same workflow run (or from another workflow run when using `workflow-run-id`).

**Key inputs:**

| Input | Required | Description |
|-------|----------|-------------|
| `name` | No | Artifact name to download. If not specified, downloads ALL artifacts from the run. |
| `path` | No | Destination directory (default: `$GITHUB_WORKSPACE`). |
| `github-token` | No | Token for cross-workflow artifact downloads (rarely needed). |
| `run-id` | No | Download from a specific run instead of the current run. |

**Important in v4 (vs. v3):**
- v4 requires explicit `name:` when you want a specific artifact (no more merging all artifacts)
- v4 preserves the original file structure without flattening
- v4 is faster and uses less storage (streaming instead of ZIP-in-memory)

**Download behavior:**
- If `name` matches one artifact, only that artifact is downloaded
- If `name` is not specified, ALL artifacts from the run are downloaded (use with caution — may be slow)
- If the artifact was uploaded from a directory, the directory structure is preserved

### Why This Approach

**Single node for linting:** Linting and type checking operate on source code, not runtime behavior. There is no difference in lint results between Node 18, 20, and 22. Running lint across all three nodes would triple CI time with zero additional signal.

**Artifact download instead of cache restore:** Artifacts are faster for same-run data transfer. Cache requires an HTTP request to query keys, then a download. Artifacts are direct downloads with no lookup overhead.

**Sequential lint → typecheck:** ESLint and TypeScript are independent tools. They could run in parallel, but on a single runner there's no benefit (the runner has one CPU). Running them sequentially is simpler and equally fast.

---

## 9. Job 4: docker-prepare

### YAML

```yaml
# =============================================================================
# Job 4: docker-prepare — Pre-build Docker Layers
# =============================================================================
# Purpose: Build Docker image layers and push them to the GitHub Actions cache.
# Runs in parallel with lint for maximum pipeline efficiency.
#
# Uses Docker BuildKit's GitHub Actions cache backend (type=gha).
# Layer cache is keyed by the docker-key from cache-calc.
#
# Key design: push: false — we only build to populate the layer cache,
# not to publish an image. Actual image publishing happens in the deploy workflow.
# =============================================================================
docker-prepare:
  needs: cache-calc
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    # docker/metadata-action generates Docker image tags and labels from
    # the Git context: branch name, commit SHA, semantic version, etc.
    - name: Generate Docker metadata
      id: meta
      uses: docker/metadata-action@v5
      with:
        images: ghcr.io/${{ github.repository }}
        tags: |
          type=ref,event=branch
          type=sha,format=short
          type=raw,value=latest,enable={{is_default_branch}}

    # setup-buildx-action initializes BuildKit with default configuration
    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3

    # Build the image WITHOUT pushing (push: false).
    # cache-from: type=gha — restore cached layers from previous runs
    # cache-to: type=gha,mode=max — save ALL layers (not just final), allowing
    #   maximal cache reuse across builds. mode=max stores every intermediate
    #   layer; mode=min only stores the final image layers.
    - name: Build and cache Docker layers
      uses: docker/build-push-action@v6
      with:
        context: .
        push: false
        tags: ${{ steps.meta.outputs.tags }}
        labels: ${{ steps.meta.outputs.labels }}
        cache-from: type=gha
        cache-to: type=gha,mode=max
```

### Line-by-Line Explanation

| Line | Element | Explanation |
|------|---------|-------------|
| 1-14 | `#` comments | Documentation. Key point: no push, only cache build. |
| 15 | `docker-prepare:` | Job ID. |
| 16 | `needs: cache-calc` | Only needs `cache-calc` (for the docker-key, though it's used implicitly via `type=gha`). Does NOT need `deps-install` — this runs in parallel with `lint`. |
| 17 | `runs-on: ubuntu-latest` | Docker is only available on Linux runners (macOS/Windows runners don't support Docker out of the box). |
| 19 | Checkout | Standard checkout. |
| 21-28 | Docker metadata | Generates tags and labels for the Docker image. |
| 23 | `id: meta` | Step ID for accessing outputs. |
| 24 | `uses: docker/metadata-action@v5` | Official Docker action for generating metadata. |
| 26 | `images: ghcr.io/${{ github.repository }}` | Container registry + image name. `ghcr.io` is the GitHub Container Registry. `${{ github.repository }}` expands to `owner/repo-name`. |
| 27-29 | `tags:` | Tag generation rules. Each line is a tag type. |
| 28 | `type=ref,event=branch` | Generate a tag from the branch name (e.g., `dev`, `main`). |
| 29 | `type=sha,format=short` | Generate a tag from the short commit SHA (e.g., `sha-a1b2c3d`). |
| 30 | `type=raw,value=latest,enable={{is_default_branch}}` | Only add the `latest` tag on the default branch (main). `{{is_default_branch}}` is a template variable in metadata-action, NOT a GitHub Actions expression. |
| 32-33 | `docker/setup-buildx-action@v3` | Sets up Docker BuildKit (the modern Docker build backend). Ensures BuildKit features are available (cache mounts, multi-platform builds, etc.). |
| 35-46 | Main build step. | |
| 37 | `uses: docker/build-push-action@v6` | Official Docker build-and-push action. |
| 39 | `context: .` | Build context — the directory sent to the Docker daemon during build. |
| 40 | `push: false` | **Key:** Build the image but do NOT push to a registry. This step is purely for cache warming. |
| 41 | `tags: ${{ steps.meta.outputs.tags }}` | Tags from the metadata action (newline-separated). |
| 42 | `labels: ${{ steps.meta.outputs.labels }}` | Labels from the metadata action. |
| 43 | `cache-from: type=gha` | **Cache source:** use GitHub Actions cache as the BuildKit cache backend. Restores layers from previous runs. |
| 44 | `cache-to: type=gha,mode=max` | **Cache destination:** save layers to GitHub Actions cache. `mode=max` saves ALL layers (including intermediate); `mode=min` only saves the final image layers. `max` gives better cache hits at the cost of more cache storage. |

### Action Capability: `docker/build-push-action@v6`

**Key inputs:**

| Input | Description |
|-------|-------------|
| `context` | Build context directory |
| `push` | Push to registry (boolean) |
| `tags` | Image tags (newline or comma separated) |
| `labels` | Image metadata labels |
| `cache-from` | Cache import sources (e.g., `type=gha`, `type=registry,ref=image:cache`) |
| `cache-to` | Cache export targets (e.g., `type=gha,mode=max`) |
| `build-args` | Docker build-time variables |
| `file` | Dockerfile path (default: `{context}/Dockerfile`) |
| `platforms` | Target platforms (for multi-arch builds) |
| `provenance` | Build provenance attestation mode |
| `sbom` | SBOM generation mode |

**Cache backends:**

| Backend | Type string | Best for |
|---------|-------------|----------|
| GitHub Actions Cache | `type=gha` | Same-repo caching (free) |
| Inline (in image) | `type=inline` | Registry-backed caching |
| Registry | `type=registry,ref=img:cache` | Cross-repo or cross-platform |
| Local directory | `type=local` | Self-hosted runners with shared storage |
| S3 | `type=s3` | AWS environments |
| Azure Blob | `type=azblob` | Azure environments |

**`mode=max` vs `mode=min`:**
- `mode=max` (recommended for CI): Caches every layer created during the build. Produces the best cache hit rate but uses more cache storage.
- `mode=min`: Caches only the final image layers (like a multi-stage build result). Uses less storage but may require rebuilding some layers on cache miss.

### Why This Approach

**Parallel execution with lint:** Since `docker-prepare` only needs `cache-calc` (not `deps-install`), it runs in parallel with `lint`. This means Docker layer caching happens while linting runs, with no additional wall-clock time.

**`push: false`:** We don't want to publish images from every CI run — that's what the deploy workflow is for. We just want to populate the layer cache so that the deploy workflow builds faster.

**`type=gha` for cache:** GitHub Actions cache is free and scoped to the repository. It's the simplest cache backend for CI in GitHub Actions — no registry credentials needed.

**`mode=max`:** We save all intermediate layers. This means even if only the last few layers change (e.g., app code), the base layers (OS packages, system deps) are reused from cache.

---

## 10. Job 5: build

### YAML

```yaml
# =============================================================================
# Job 5: build — TypeScript Compilation + Vite Bundling (Matrix)
# =============================================================================
# Purpose: Compile TypeScript and bundle with Vite across 3 Node versions.
# Uses dep cache from deps-install and build cache (dist/) to enable
# incremental compilation where possible.
#
# Why matrix build:
#   - Validates that the project compiles cleanly on all target Node versions
#   - Produces version-specific dist/ artifacts for test-unit matrix
# =============================================================================
build:
  needs: deps-install
  runs-on: ubuntu-latest
  strategy:
    matrix:
      node: [18, 20, 22]
  steps:
    - uses: actions/checkout@v4

    - uses: actions/setup-node@v4
      with:
        node-version: ${{ matrix.node }}

    # Download pre-installed node_modules from the matching deps-install job
    - name: Download node_modules
      uses: actions/download-artifact@v4
      with:
        name: node_modules-${{ matrix.node }}
        path: node_modules

    # Restore previously built dist/ from cache (if any)
    # Vite/tsc can use this for persistent compilation cache
    - name: Restore build cache
      id: build-cache-restore
      uses: actions/cache/restore@v4
      with:
        path: dist
        key: ${{ needs.cache-calc.outputs.build-key }}-${{ matrix.node }}
        restore-keys: |
          ${{ needs.cache-calc.outputs.build-key }}-

    # npm run build compiles TypeScript and bundles with Vite
    # (defined in package.json as: npm run build:web && tsc && cp -r ...)
    - name: Build project
      run: npm run build

    # Upload dist/ for test-unit and test-integration jobs
    - name: Upload dist artifact
      uses: actions/upload-artifact@v4
      with:
        name: dist-${{ matrix.node }}
        path: dist/
        retention-days: 3
```

### Line-by-Line Explanation

| Line | Element | Explanation |
|------|---------|-------------|
| 1-15 | `#` comments | Documentation header. |
| 16 | `build:` | Job ID. |
| 17 | `needs: deps-install` | Depends on `deps-install`. Does NOT depend on `lint` or `docker-prepare` — those run in parallel. |
| 18 | `runs-on: ubuntu-latest` | Linux runner. |
| 19-22 | Matrix `node: [18, 20, 22]` | Same 3-node matrix as `deps-install`. |
| 24-25 | Checkout | Standard. |
| 27-31 | Setup Node | No `cache: npm` needed (we download node_modules from artifact, don't run npm ci). |
| 33-38 | Download `node_modules` | Downloads from the matching deps-install. The artifact name `node_modules-${{ matrix.node }}` ensures node 20 build gets node 20's node_modules. |
| 40-48 | Build cache restore | Restores previously built `dist/` from cache if available. |
| 44 | `key: ${{ needs.cache-calc.outputs.build-key }}-${{ matrix.node }}` | Build cache key. Chained: includes source file hash AND lockfile hash. If either source or deps changed, the key changes. |
| 46 | `restore-keys: \| ${{ needs.cache-calc.outputs.build-key }}-` | Fallback: any previous build from the same source hash (any node version — useful for partial restore). |
| 50-51 | Build | Runs `npm run build`. |
| 53-58 | Upload `dist/` artifact | Uploads built output for downstream test jobs. |

### Cache Key Chaining in Action

The build key is `build-<source-hash>-<dep-hash>`. This means:

```
Scenario: Only source code changes
  build-key: build-a1b2c-d4e5f → cache MISS (source hash changed)
  restore-key: build-a1b2c- → partial hit from previous build with same source
  → Build runs, some cache may be reused via tsc incremental

Scenario: Only dependencies change (package-lock.json)
  build-key: build-a1b2c-d4e6f → cache MISS (dep hash changed due to lockfile)
  Source hash a1b2c is the same, but dep hash changed
  → Full rebuild needed (new deps may change compilation)

Scenario: Nothing changed
  build-key: build-a1b2c-d4e5f → cache HIT
  → Restore dist/ from cache, skip build entirely
  → (If build step still runs, tsc incremental compilation is fast)
```

### Why Artifact vs Cache for `dist/`

Both `dist/` and `node_modules/` use artifacts for same-run pass-through and cache for cross-run warming. The distinction:

| Mechanism | Use Case | Speed | Persistence |
|-----------|----------|-------|-------------|
| **Cache** | Cross-run (first CI on a branch) | Slower (key lookup) | Days (based on LRU eviction) |
| **Artifact** | Same-run (current workflow) | Faster (direct download) | Configured by `retention-days` |

The `build` job's cache restore provides a cold-start benefit: if you push a branch and the first CI run finds a cache from a previous main build, `dist/` is restored in seconds. But within the current workflow run, `test-unit` and `test-integration` download `dist/` as an artifact.

---

## 11. Job 6: test-unit

### YAML

```yaml
# =============================================================================
# Job 6: test-unit — Unit Tests with Matrix Sharding
# =============================================================================
# Purpose: Run unit tests across 3 Node versions x 2 OS variants x 2 shards.
# This is the most heavily parallelized job in the pipeline.
#
# Sharding strategy:
#   - Vitest --shard=N/M splits test files across M shards
#   - Total wall-clock time becomes max(shard_time), not sum(all_test_times)
#   - With 2 shards across 6 (node x os) variants = up to 12 parallel runners
#
# fail-fast: false — one failing combination doesn't cancel others,
# allowing us to see which combinations pass and which fail.
# =============================================================================
test-unit:
  needs: build
  runs-on: ${{ matrix.os }}
  strategy:
    matrix:
      node: [18, 20, 22]
      os: [ubuntu-latest, windows-latest]
      # 2 shards per node+os combination = 2x coverage without 2x wall clock
      shard: [1, 2]
    # Exclude windows + node 18: reduces CI costs while still testing the
    # most important combinations (win+20, win+22, all ubuntu combos)
    exclude:
      - os: windows-latest
        node: 18
    # Don't cancel all runners when one fails — we want signal from every combo
    fail-fast: false
  steps:
    - uses: actions/checkout@v4

    - uses: actions/setup-node@v4
      with:
        node-version: ${{ matrix.node }}

    # Download pre-built dist/ from the matching build job
    - name: Download dist artifact
      uses: actions/download-artifact@v4
      with:
        name: dist-${{ matrix.node }}
        path: dist

    # node_modules is needed for test framework and type resolution
    - name: Download node_modules
      uses: actions/download-artifact@v4
      with:
        name: node_modules-${{ matrix.node }}
        path: node_modules

    # Vitest sharding: https://vitest.dev/guide/cli.html#shard
    # --shard=1/2 runs the first half of test files
    # --shard=2/2 runs the second half
    - name: Run unit tests (shard ${{ matrix.shard }}/2)
      run: npx vitest run --shard=${{ matrix.shard }}/2

    # Upload test results even on failure (if: always()) for debugging
    - name: Upload test results
      if: always()
      uses: actions/upload-artifact@v4
      with:
        name: test-results-${{ matrix.node }}-${{ matrix.os }}-shard${{ matrix.shard }}
        path: test-results/
        retention-days: 7
```

### Line-by-Line Explanation

| Line | Element | Explanation |
|------|---------|-------------|
| 1-18 | `#` comments | Documentation. |
| 19 | `test-unit:` | Job ID. |
| 20 | `needs: build` | Depends on the `build` job (ALL matrix variants of build must complete). |
| 21 | `runs-on: ${{ matrix.os }}` | **Key:** The runner OS is controlled by the matrix. Jobs with `os: windows-latest` run on Windows; `os: ubuntu-latest` run on Linux. This tests cross-platform compatibility. |
| 22-35 | `strategy:` block | Complex matrix with excludes. |
| 24-28 | `matrix:` dimensions | Three dimensions: `node` (3 values), `os` (2 values), `shard` (2 values). Theoretical total: 3 × 2 × 2 = 12 combinations. |
| 25 | `node: [18, 20, 22]` | Node versions. |
| 26 | `os: [ubuntu-latest, windows-latest]` | Operating systems. |
| 28 | `shard: [1, 2]` | Test shard indices. |
| 30-31 | `exclude:` | Removes specific combinations from the matrix. |
| 31 | `- os: windows-latest, node: 18` | Removes the (windows, node 18) combination — 2 shard values × 1 exclusion = 2 fewer jobs. |
| 33-34 | `fail-fast: false` | **Critical:** When one matrix job fails, do NOT cancel the remaining in-progress jobs. Without this, a Node 18 failure would cancel the Node 22 job that's still running. |

#### How the Matrix Expands

Without exclude:
```
(18, ubuntu, 1)  (18, ubuntu, 2)  (18, windows, 1)  (18, windows, 2)
(20, ubuntu, 1)  (20, ubuntu, 2)  (20, windows, 1)  (20, windows, 2)
(22, ubuntu, 1)  (22, ubuntu, 2)  (22, windows, 1)  (22, windows, 2)
```
= 12 jobs

With exclude `(windows, 18)`:
```
(18, ubuntu, 1)  (18, ubuntu, 2)  ~~(18, windows, 1)~~  ~~(18, windows, 2)~~
(20, ubuntu, 1)  (20, ubuntu, 2)  (20, windows, 1)  (20, windows, 2)
(22, ubuntu, 1)  (22, ubuntu, 2)  (22, windows, 1)  (22, windows, 2)
```
= 10 jobs

#### Steps

| Line | Element | Explanation |
|------|---------|-------------|
| 37-38 | Checkout | Standard. |
| 40-44 | Setup Node | Uses `matrix.node`. |
| 46-51 | Download `dist/` | Downloads from the matching build job. E.g., for `(node: 20, os: windows)`, downloads `dist-20`. |
| 53-58 | Download `node_modules` | Downloads from `deps-install` for `matrix.node`. |
| 60-63 | Vitest sharded run | Runs vitest in shard mode. |
| 62 | `run: npx vitest run --shard=${{ matrix.shard }}/2` | Vitest splits test files into 2 groups. `--shard=1/2` runs the first half, `--shard=2/2` runs the second half. |
| 65-72 | Upload results | Uploads test result files (JUnit XML, coverage, etc.) even if tests failed (`if: always()`). |
| 67 | `if: always()` | This expression makes the step run regardless of the previous step's outcome. Without this, a test failure would skip the upload step. |
| 69 | `name: test-results-${{ matrix.node }}-${{ matrix.os }}-shard${{ matrix.shard }}` | Unique artifact name per combination. Example: `test-results-20-windows-latest-shard1`. |
| 71 | `retention-days: 7` | Longer retention for test results (you may want to review them after the 1-3 day CI artifact window expires). |

### Action Capability: Matrix Strategies

**Full `strategy` syntax:**

```yaml
strategy:
  matrix:
    <dimension>: [<values>]
    <dimension>: [<values>]
  include:
    - <dimension>: <value>
      <extra-key>: <value>    # Adds extra variables to specific combinations
  exclude:
    - <dimension>: <value>    # Removes specific combinations
  fail-fast: true|false       # Cancel all jobs when one fails (default: true)
  max-parallel: <number>      # Limit concurrent matrix jobs (default: unlimited)
```

**`include` usage:**

The `include` keyword adds custom combinations or adds extra variables to existing ones:

```yaml
strategy:
  matrix:
    node: [18, 20]
    os: [ubuntu]
  include:
    - node: 20
      os: windows
      experimental: true    # Extra variable only for this combo
    - node: 22              # Entirely new combination
      os: ubuntu
```

**Key matrix concepts:**
- Matrix jobs are FULLY INDEPENDENT — they run in separate runner instances
- Each job has its own `${{ matrix.<dimension> }}` values
- Matrix jobs all share the same `needs:` block
- `fail-fast` is per-matrix-instance, not per-workflow

### Action Capability: `if:` Conditional

The `if:` keyword controls whether a step or job runs:

```yaml
if: <expression>
```

**Common patterns:**

| Expression | Behavior |
|------------|----------|
| `always()` | Run regardless of previous step success/failure. Steps still fail if the runner is broken. |
| `success()` | Run only if all previous steps succeeded (default behavior). |
| `failure()` | Run only if a previous step failed. |
| `cancelled()` | Run only if the workflow was cancelled. |
| `github.ref == 'refs/heads/main'` | Only on main branch. |
| `steps.my-step.outputs.cache-hit != 'true'` | Only on cache miss. |

**Combining conditions:**
```yaml
if: always() && !cancelled()
if: failure() || github.event_name == 'workflow_dispatch'
```

### Why Sharding?

Without sharding, if you have 100 test files and 4 runners, the wall-clock time is the SUM of all test runtimes on one runner:

```
Test runtime without sharding: 10 minutes (all tests on one runner)
```

With 2 shards across each of 5 (node x os) combinations:

```
Shard 1: 50 test files → 5 minutes
Shard 2: 50 test files → 5 minutes
Wall clock: 5 minutes (half the time)
```

Sharding is beneficial when:
- You have many test files (>100)
- Tests are CPU-bound, not I/O-bound
- You have available CI parallelism
- Test suite runtime is a bottleneck in your pipeline

### Why `fail-fast: false`?

**Without `fail-fast: false` (default `true`):**
```
Job (18, windows) fails
→ All other 9 jobs are cancelled immediately
→ You only know that (18, windows) failed
→ You have no signal on (20, ubuntu), (22, windows), etc.
```

**With `fail-fast: false`:**
```
Job (18, windows) fails
→ Other 9 jobs continue running
→ You see results for ALL combinations
→ Node 20 passes on both OS, Node 22 passes on Linux but fails on Windows
```

For CI, `fail-fast: false` is usually better. The extra CI minutes spent running to completion are worth the comprehensive signal. Use `fail-fast: true` only when CI minutes are scarce and speed is critical.

---

## 12. Job 7: test-integration

### YAML

```yaml
# =============================================================================
# Job 7: test-integration — Integration Tests with Docker Compose
# =============================================================================
# Purpose: Spin up the full service stack via Docker Compose and run
# integration tests against it. This validates that the build artifact
# works correctly in a containerized environment with real dependencies.
#
# Key design:
#   - Uses the node 20 dist/ artifact (one representative version)
#   - Docker Compose controls service lifecycle
#   - Container logs are collected on failure for debugging
#   - Teardown always runs (if: always()) to prevent resource leaks
# =============================================================================
test-integration:
  needs: build
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - uses: actions/setup-node@v4
      with:
        node-version: ${{ env.NODE_VERSION }}

    # Download pre-built dist/ (node 20) and matching node_modules
    - name: Download dist artifact
      uses: actions/download-artifact@v4
      with:
        name: dist-${{ env.NODE_VERSION }}
        path: dist

    - name: Download node_modules
      uses: actions/download-artifact@v4
      with:
        name: node_modules-${{ env.NODE_VERSION }}
        path: node_modules

    # Start all services defined in docker-compose.yml
    # --wait: wait for health checks to pass before proceeding
    # --wait-timeout: maximum seconds to wait for services to become healthy
    - name: Start Docker Compose services
      run: docker compose up -d --wait --wait-timeout 60

    # Integration test command (defined in package.json — create if not present)
    - name: Run integration tests
      run: npx vitest run --config vitest.integration.config.ts 2>/dev/null || npm run test:integration 2>/dev/null || echo "No integration tests configured yet"

    # Collect logs from all containers for debugging test failures
    - name: Collect container logs
      if: failure()
      run: docker compose logs --tail=100

    # Always tear down, regardless of test outcome
    - name: Teardown Docker Compose
      if: always()
      run: docker compose down -v --remove-orphans
```

### Line-by-Line Explanation

| Line | Element | Explanation |
|------|---------|-------------|
| 1-16 | `#` comments | Documentation header. |
| 17 | `test-integration:` | Job ID. |
| 18 | `needs: build` | Depends on the `build` job (waits for all matrix variants). |
| 19 | `runs-on: ubuntu-latest` | Docker is only available on Linux runners. |
| 21-22 | Checkout | Standard. |
| 24-28 | Setup Node | Uses the default `NODE_VERSION` (20). |
| 30-35 | Download `dist/` | Downloads `dist-20` artifact. |
| 37-41 | Download `node_modules` | Downloads `node_modules-20` artifact. |
| 43-46 | Docker Compose start | |
| 45 | `docker compose up -d --wait --wait-timeout 60` | `-d`: detached mode (run in background). `--wait`: wait for all services to pass health checks before proceeding. `--wait-timeout 60`: fail if services aren't healthy within 60 seconds. |
| 48-50 | Integration tests | Runs integration tests. Uses `\|\|` fallbacks for graceful handling if the integration test config doesn't exist yet. |
| 49 | Command explanation: | Tries vitest with integration config first, falls back to `test:integration` npm script, then gracefully prints a message if neither exists. |
| 52-55 | Collect logs on failure | |
| 53 | `if: failure()` | Only runs if a previous step failed. |
| 54 | `docker compose logs --tail=100` | Prints the last 100 lines of each container's log. |
| 57-60 | Teardown | |
| 58 | `if: always()` | Runs even if tests failed. This is critical for cleanup. |
| 59 | `docker compose down -v --remove-orphans` | `down`: stop and remove containers. `-v`: remove volumes. `--remove-orphans`: clean up containers not defined in the compose file. |

### Docker Compose Lifecycle Management

The standard pattern for integration tests with Docker Compose:

```
           [start]                    [failure]              [always]
  Checkout ──> docker compose up ──> test run ──> collect logs ──> docker compose down
                     │                                             ↑
                     └────── wait for health ──────────────────────┘
```

**Why `--wait` matters:** Without `--wait`, `docker compose up -d` returns immediately, and the next step (tests) might run before the database is accepting connections. The health check ensures:

1. Container is running
2. Internal process is ready (e.g., PostgreSQL accepts connections)
3. Application responds to health endpoints

**Why `if: always()` for teardown:** If tests fail and the runner doesn't tear down Docker, resources leak. On GitHub Actions hosted runners, the entire VM is destroyed after the job, so leaks aren't permanent, but:
- Running containers consume disk space
- Running containers may hold ports
- Volumes take up space that could be used for artifact downloads

**Why `--remove-orphans`:** If the workflow run is a retry, there might be leftover containers from previous runs with different service configurations.

### Why Single Node for Integration Tests?

Integration tests validate BEHAVIOR, not runtime compatibility. The core logic should behave identically across Node versions. Running integration tests on one representative version (20 LTS) is sufficient, and the unit test matrix already covers Node version-specific issues.

---

## 13. Job 8: cache-warm

### YAML

```yaml
# =============================================================================
# Job 8: cache-warm — Prime Caches for Future Runs (main branch only)
# =============================================================================
# Purpose: After a successful build on main, explicitly save all cache layers.
# This ensures PR branches based on main get full cache hits, even if the
# previous main run's caches expired or were evicted.
#
# Why explicit save:
#   - actions/cache only saves on cache miss (post-action). If main ran with
#     a cache hit, the post-action skip means no new cache entry is written.
#   - cache-warm guarantees fresh cache entries after every main merge.
#   - Running `npm ci` here creates the exact expected node_modules to cache.
#
# Condition: github.ref == 'refs/heads/main' ensures this only runs on main,
# not on PR or dev branches (where it would waste CI minutes).
# =============================================================================
cache-warm:
  if: github.ref == 'refs/heads/main'
  needs: [cache-calc, test-unit, test-integration]
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - uses: actions/setup-node@v4
      with:
        node-version: ${{ env.NODE_VERSION }}
        cache: npm

    # Fresh npm ci to produce node_modules that exactly matches the lockfile
    - name: Install dependencies
      run: npm ci

    # Explicitly save node_modules cache with the exact dep-key
    # This overwrites any stale cache entry with the same key
    - name: Prime dependency cache
      uses: actions/cache/save@v4
      with:
        path: node_modules
        key: ${{ needs.cache-calc.outputs.dep-key }}-${{ env.NODE_VERSION }}

    # Also prime the build cache by running the build and saving dist/
    - name: Build project
      run: npm run build

    - name: Prime build cache
      uses: actions/cache/save@v4
      with:
        path: dist
        key: ${{ needs.cache-calc.outputs.build-key }}-${{ env.NODE_VERSION }}
```

### Line-by-Line Explanation

| Line | Element | Explanation |
|------|---------|-------------|
| 1-18 | `#` comments | Documentation explaining the purpose and design rationale. |
| 19 | `cache-warm:` | Job ID. |
| 20 | `if: github.ref == 'refs/heads/main'` | **Job-level condition.** If the expression evaluates to `false`, the ENTIRE JOB is skipped (shows as "skipped" in the UI, not "failed"). The condition checks whether the current ref is the main branch. |
| 21 | `needs: [cache-calc, test-unit, test-integration]` | Depends on THREE jobs (array syntax). Cache-warming only happens after ALL tests pass on main. `cache-calc` is included because we reference `needs.cache-calc.outputs.*`. |
| 22 | `runs-on: ubuntu-latest` | Linux runner. |
| 24-25 | Checkout | Standard. |
| 27-31 | Setup Node with `cache: npm` | Here we DO use `cache: npm` because we're running `npm ci` from scratch. |
| 33-34 | `npm ci` | Fresh install to produce the exact `node_modules/` we want to cache. |
| 36-41 | Save dep cache | |
| 38 | `uses: actions/cache/save@v4` | The save-only sub-action. Unlike the full `actions/cache` (which saves as a post-action), this saves IMMEDIATELY. |
| 40 | `key: ${{ needs.cache-calc.outputs.dep-key }}-${{ env.NODE_VERSION }}` | The exact key that future PR runs will look up. By saving this explicitly on main, we guarantee the cache exists for the next PR. |
| 43-44 | `npm run build` | Run the build to produce `dist/`. |
| 46-51 | Save build cache | Same pattern: explicitly save `dist/` with the build key. |

### Action Capability: `actions/cache/save@v4`

**Purpose:** Explicitly save a cache entry immediately (not as a post-action).

**Key inputs:**

| Input | Required | Description |
|-------|----------|-------------|
| `path` | Yes | Directory/file to cache |
| `key` | Yes | Cache key (must be unique) |
| `upload-chunk-size` | No | Chunk size for large cache uploads |

**Constraints:**
- Maximum cache size per entry: ~10 GB (varies by plan)
- Maximum number of entries: no hard limit, but LRU eviction applies
- Keys must be unique per entry (new save with existing key overwrites)
- Cache entries expire after 7 days of no access (adjustable by GitHub support)

### `actions/cache/save` vs Post-Action Save

The full `actions/cache` action has two phases:

1. **Pre-action (restore):** Runs BEFORE the step that uses `actions/cache`. Restores cache if key matches.
2. **Post-action (save):** Runs AFTER the job completes. Saves the cache ONLY if the key was new (not a cache hit).

**The problem this creates:**

```
Run 1 (main, cache MISS):
  Step: actions/cache → restore: miss
  Step: npm ci → creates node_modules
  Post-action: cache/save → saves node_modules with key X
  → Cache entry X exists ✓

Run 2 (main, cache HIT — same commit re-run):
  Step: actions/cache → restore: hit → node_modules restored
  Step: npm ci → verifies (fast, no changes)
  Post-action: cache/save → SKIPS (was a cache hit)
  → Cache entry X still exists, but with original TTL ✓

Run 3 (main, cache miss after cache eviction 8 days later):
  Step: actions/cache → restore: miss (entry X was evicted)
  Step: npm ci → installs from scratch
  Post-action: cache/save → saves new entry X
  → Works, but slow for the first PR after eviction ✗
```

**The `cache-warm` fix:**

```
Run N (main):
  → cache-warm job runs
  → actions/cache/save with key X → overwrites/creates entry
  → Cache entry X is fresh with new TTL
  
Run N+1 (PR branch based on main):
  → deps-install looks up key X → HIT
  → node_modules restored in seconds ✓
```

### Action Capability: `if:` on Jobs vs Steps

**Job-level `if:`:**
```yaml
jobs:
  my-job:
    if: <condition>
    ...
```
- Controls whether the ENTIRE job runs
- If `false`, the job shows as "skipped" in the UI
- All job dependencies (`needs:`) must still complete (or be skipped)
- Expressions can reference `github`, `env`, `needs`, etc.

**Step-level `if:`:**
```yaml
steps:
  - name: My step
    if: <condition>
    ...
```
- Controls whether a single step runs
- If `false`, the step is skipped but subsequent steps still run
- `if: always()` overrides failure status

### Why This Pattern Matters

Without `cache-warm`, the cache on main branch degrades over time:

```
Day 1: Cache entry created (good)
Day 7: Cache entry expires (LRU eviction or TTL)
Day 8: First PR → cache miss → slow npm ci → slow pipeline
```

With `cache-warm`, every successful main merge refreshes the cache:

```
Day 1: Cache entry created
Day 2: Merge to main → cache-warm → entry refreshed
Day 7: Merge to main → cache-warm → entry refreshed (never expires)
Day 8: First PR → cache HIT → fast pipeline
```

This is especially important for repositories with periodic but not continuous CI activity.

---

## 14. Expression Syntax and Context Objects

### The `${{ }}` Expression Delimiter

GitHub Actions expressions are enclosed in `${{ }}`. The expression parser evaluates these before the workflow run begins.

```yaml
# Examples throughout the workflow:
${{ hashFiles('package-lock.json') }}
${{ runner.os }}
${{ matrix.node }}
${{ needs.cache-calc.outputs.dep-key }}
${{ github.ref }}
${{ github.workflow }}
${{ env.NODE_VERSION }}
${{ matrix.os }}
```

**Rules:**
- Expressions can appear in ANY workflow field (not just `run:`)
- Expression results are automatically converted to strings
- If an expression is used in a `run:` command, it's evaluated server-side and the result is embedded in the shell command
- Literal `$` must be escaped as `$$` or `${{ '#' }}` depending on context

### Available Context Objects

| Context | Description | Common Properties |
|---------|-------------|-------------------|
| `github` | Information about the workflow run and event | `github.ref`, `github.sha`, `github.repository`, `github.actor`, `github.event_name`, `github.workflow`, `github.run_id`, `github.run_number` |
| `env` | Environment variables defined in workflow/job/step | `env.MY_VAR` |
| `runner` | Information about the runner | `runner.os`, `runner.arch`, `runner.name`, `runner.temp` |
| `matrix` | Current matrix values | `matrix.node`, `matrix.os`, `matrix.shard` |
| `needs` | Outputs from dependent jobs | `needs.cache-calc.outputs.dep-key` |
| `steps` | Outputs from previous steps | `steps.my-step.outputs.cache-hit` |
| `secrets` | Repository/organization secrets | `secrets.GITHUB_TOKEN` |
| `inputs` | Workflow dispatch inputs | `inputs.my-input` |
| `strategy` | Matrix strategy info | `strategy.job-index`, `strategy.job-total`, `strategy.max-parallel` |

### Functions Available in Expressions

| Function | Description | Example |
|----------|-------------|---------|
| `hashFiles()` | SHA-256 hash of file contents | `hashFiles('package.json')` |
| `contains()` | Check if string/array contains value | `contains('hello', 'ell')` |
| `startsWith()` | Check if string starts with value | `startsWith(github.ref, 'refs/heads/')` |
| `endsWith()` | Check if string ends with value | `endsWith(github.ref, '/main')` |
| `format()` | String formatting | `format('{0} {1}', 'hello', 'world')` |
| `join()` | Join array with separator | `join(github.commits, ', ')` |
| `toJSON()` | Pretty-print JSON | `toJSON(github)` |
| `fromJSON()` | Parse JSON string | `fromJSON(inputs.my-json)` |
| `success()` | Did all previous steps succeed? | `success()` |
| `failure()` | Did any previous step fail? | `failure()` |
| `cancelled()` | Was the workflow cancelled? | `cancelled()` |
| `always()` | Always true | `always()` |

### Operator Precedence and Type Coercion

Expressions support:
- **Comparison:** `==`, `!=`, `<`, `>`, `<=`, `>=`
- **Boolean:** `&&`, `||`, `!`
- **Ternary:** `condition ? true-value : false-value`
- **Null-coalescing:** `value ?? default-value`

**Type coercion rules:**

```yaml
# String comparison (default — most values in GitHub Actions are strings)
'false' == 'true'   → false
'false' == false    → false (string != boolean)

# Boolean comparison (use `true`/`false` without quotes)
true && false       → false
true || false       → true

# In conditions, unquoted strings are treated as literal values
if: true            → runs
if: false           → skipped
if: 'true'          → ERROR (string not allowed in if:)
```

**Important:** In `if:` blocks, you must use unquoted booleans:
```yaml
# CORRECT
if: true
if: false
if: success()

# INCORRECT
if: 'true'   # treated as a string, which is truthy → always runs!
```

### The `needs` Context in Detail

The `needs` context is one of the most important for complex workflows:

```yaml
# Accessing outputs from a non-matrix job:
${{ needs.cache-calc.outputs.dep-key }}

# Accessing outputs from a matrix job — requires specific index:
# This is NOT possible directly. Matrix job outputs must be aggregated.
```

**Matrix job outputs limitation:** When a matrix job declares `outputs:`, each matrix variant tries to set the same output. The last one to complete wins. This makes matrix outputs unreliable. Workarounds:
1. Use artifacts instead of outputs for matrix data
2. Use a non-matrix "aggregator" job that reads artifacts and produces outputs
3. Accept the last-write-wins behavior

### The `hashFiles` Function in Detail

The `hashFiles()` function is evaluated on the ACTIONS SERVER, not on the runner. This has implications:

```yaml
# hashFiles only works with files in the workspace.
# It returns different values depending on:
# 1. The file contents (obviously)
# 2. The file paths matched by the glob
# 3. The line ending normalization (Git checkout settings)

# Best practices:
# - Always checkout before hashFiles in the same job
# - Use platform-independent patterns (forward slashes)
# - Don't include node_modules or dist in hash patterns
```

**Performance note:** `hashFiles()` with recursive globs (`src/**/*.ts`) can be slow in large repositories. If you have 10,000+ TypeScript files, consider a more targeted pattern. In our case `src/` is small enough that this isn't a concern.

---

## 15. Key Patterns Summary

### Pattern 1: Cache Key Chaining

```
dep-key = npm-cache-<lockfile-hash>-<OS>
build-key = build-<source-hash>-<dep-hash>
docker-key = docker-<dockerfile-hash>-<dep-hash>
test-key = test-<test-hash>
```

Build depends on dep → when deps change, build cache auto-invalidates.

### Pattern 2: Cache Restore with Fallbacks

```yaml
key: specific-key-with-all-details
restore-keys: |
  prefix-with-fewer-details-
  even-broader-prefix-
```

GitHub Actions tries `key` first, then each `restore-keys` prefix in order, returning the most recently created cache matching each prefix. This provides graceful degradation: best case = exact hit, worst case = no cache.

### Pattern 3: Artifact Pass-Through

```
              ┌──────────────┐
              │ deps-install │──→ node_modules artifact
              └──────┬───────┘
                     │
              ┌──────▼───────┐
              │    build      │──→ dist artifact
              └──────┬───────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
   test-unit    test-integ    (other jobs)
```

Artifacts flow forward. Each job produces an artifact consumed by the next stage.

### Pattern 4: Explicit Cache Save for Main Branch

After all tests pass on main, `cache-warm` explicitly saves caches. This:
- Guarantees cache entries exist for the next PR
- Refreshes TTL on existing entries
- Avoids cold-start slowness

### Pattern 5: Matrix with Exclude for Cost Management

```yaml
matrix:
  node: [18, 20, 22]
  os: [ubuntu, windows]
exclude:
  - os: windows
    node: 18
```

This tests the broadest range while excluding expensive or low-value combinations.

### Pattern 6: Parallel Fast-Feedback + Slow Jobs

```
cache-calc (fast, single)
    ├── deps-install (matrix, slow) ──→ build (matrix, slow) ──→ tests (parallel)
    ├── lint (fast, single)
    └── docker-prepare (fast, single)
```

The critical path from `deps-install` through `build` to `tests` determines the total wall-clock time. Fast jobs (`lint`, `docker-prepare`) run in parallel and don't extend the critical path.

### Pattern 7: Graceful Failure Handling

| Technique | Example | Purpose |
|-----------|---------|---------|
| `if: always()` | Teardown steps | Ensure cleanup runs even after failure |
| `if: failure()` | Log collection | Run debugging steps only when needed |
| `fail-fast: false` | Test matrix | Get signal from all combinations |
| `\|\| fallback` | Integration test command | Handle missing test configs gracefully |

---

## Appendix: Workflow Configuration and Tuning

### Cache Size Management

GitHub Actions cache storage is limited per repository (varies by plan, typically 10 GB). Our workflow uses cache in three places:

| Cache | Scope | Estimated Size | Frequency |
|-------|-------|---------------|-----------|
| Dependency cache (node_modules) | Per-node-version | 100-500 MB | Every main merge |
| Build cache (dist/) | Per-node-version | 5-50 MB | Every main merge |
| Docker layer cache | Shared | 200-2000 MB | Every main merge |

**Tuning tips:**
- Monitor cache usage in GitHub UI under "Actions > Caches"
- If approaching the cache limit, reduce cache scope or increase eviction priority
- Docker layer cache tends to be the largest contributor — consider using `mode=min` instead of `mode=max` to reduce size at the cost of cache hit rate
- Artifact storage has a separate limit — use `retention-days: 1` for intermediate artifacts

### Adjusting Matrix Scope

The current workflow runs up to 3 (deps-install) + 3 (build) + 10 (test-unit) + 1 (lint) + 1 (docker-prepare) + 1 (test-integration) + 1 (cache-warm) = 20 parallel jobs. This is within typical GitHub Actions limits but may hit concurrency limits on smaller plans.

**To reduce concurrency:**
```yaml
# Add max-parallel to strategy
strategy:
  max-parallel: 5
```

**To target specific Node versions:**
```yaml
# Only latest two LTS versions
matrix:
  node: [20, 22]
```

**To reduce OS coverage:**
```yaml
# Linux-only testing (drop Windows)
matrix:
  node: [18, 20, 22]
  os: [ubuntu-latest]
  shard: [1, 2]
```

### Monitoring Workflow Performance

Key metrics to track:

| Metric | What It Measures | Target |
|--------|-----------------|--------|
| Total wall-clock time | Time from trigger to completion | < 10 min |
| Cache hit rate | Percentage of cache restores that hit | > 80% |
| Artifact transfer time | Time to upload/download artifacts | < 30s |
| Test shard imbalance | Difference between fastest and slowest shard | < 20% |

To monitor cache hit rate, add this step to any cache-restoring job:

```yaml
- name: Report cache status
  if: always()
  run: echo "Cache hit: ${{ steps.deps-cache-restore.outputs.cache-hit }}"
```

### Environment-Specific Configuration

The workflow uses `env.NODE_VERSION` (20) as the default. For projects with different LTS schedules:

```yaml
env:
  NODE_VERSION: 18    # For projects requiring older LTS
  NODE_LTS: 20        # Latest LTS
```

For monorepos with multiple packages, the `hashFiles()` patterns may need adjustment:

```yaml
# For a monorepo with packages/ directory:
hashFiles('packages/*/package-lock.json', 'package-lock.json')
```

---

## Appendix: Alternative Approaches and Design Tradeoffs

### Approach A: Centralized Key Computation (Our Choice)

**How it works:** One job computes all cache keys, downstream jobs read them via `needs.outputs`.

**Pros:**
- Single point of truth for key computation logic
- Consistent patterns across all jobs
- Easy to audit and modify

**Cons:**
- Adds one sequential job to the critical path (15-30s)
- Key computation is separated from usage (cognitive overhead)
- Matrix jobs must construct their own keys with appended matrix values

**Best for:** Teams that value consistency and auditability. Large workflows with many cache consumers.

### Approach B: Distributed Key Computation

**How it works:** Each job computes its own cache key using `hashFiles()` directly, with no shared key job.

```yaml
deps-install:
  steps:
    - uses: actions/checkout@v4
    - id: compute
      run: echo "key=npm-cache-${{ hashFiles('package-lock.json') }}-${{ runner.os }}-${{ matrix.node }}" >> "$GITHUB_OUTPUT"
    - uses: actions/cache@v4
      with:
        key: ${{ steps.compute.outputs.key }}
```

**Pros:**
- Simpler DAG (one fewer job)
- Keys naturally include matrix values
- No cross-job output wiring

**Cons:**
- Key computation logic duplicated across jobs
- Drift risk: different patterns for the "same" key
- Harder to audit (must check every job)

**Best for:** Small workflows with 2-3 jobs. Prototypes and simple CI setups.

### Approach C: Hybrid (Keys in Env Vars)

**How it works:** Compute keys at the workflow level using `env:` and `hashFiles()`:

```yaml
env:
  DEP_KEY: npm-cache-${{ hashFiles('package-lock.json') }}
```

**Why this doesn't work:** `hashFiles()` in `env:` is evaluated at a different point in the workflow lifecycle and may not have access to the checkout. GitHub Actions does not support `hashFiles()` in the top-level `env:` block reliably.

**Best for:** Nothing — it doesn't work reliably. Avoid this pattern.

### Approach D: Artifact-Only (No Cache)

**How it works:** Use artifacts for all pass-through, skip `actions/cache` entirely.

**Pros:**
- Simpler setup (no cache keys)
- No cache storage costs
- No cache eviction concerns

**Cons:**
- No cross-run persistence: every first push to a branch starts from scratch
- Artifacts are deleted after `retention-days`
- Slower than cache for cross-run scenarios

**Best for:** Repositories with very infrequent CI runs where cache efficiency is irrelevant.

### Why We Chose Approach A

For this workflow, the centralized approach wins because:
1. **Auditability:** One `cache-calc` job documents ALL cache key patterns
2. **Consistency:** Every job reads from the same source — no drift
3. **Educational value:** Demonstrates job outputs, needs chaining, and expression composition
4. **Production readiness:** The slight overhead of one extra job is negligible compared to total build time (15s vs 5-8 min)

### Sharding Strategy Comparison

| Strategy | Shard mechanism | Setup complexity | Load balance |
|----------|----------------|------------------|--------------|
| Vitest `--shard` | Built into test runner | Low | Good (file-level) |
| Jest `--shard` | Built into test runner | Low | Good (file-level) |
| Manual file splitting | Custom script | High | Best (test-level) |
| `github.graphql` query | Query API for files | High | Poor (no test weighting) |

Vitest sharding is the recommended approach for projects already using Vitest. It requires no custom infrastructure and provides deterministic file splitting.

---

## Appendix: Common GitHub Actions Pitfalls

### Pitfall 1: `hashFiles` Without Checkout

```yaml
# WRONG — hashFiles returns empty string (no files found)
steps:
  - id: compute
    run: echo "hash=${{ hashFiles('package.json') }}" >> "$GITHUB_OUTPUT"

# CORRECT — checkout first
steps:
  - uses: actions/checkout@v4
  - id: compute
    run: echo "hash=${{ hashFiles('package.json') }}" >> "$GITHUB_OUTPUT"
```

### Pitfall 2: String vs Boolean in `if:`

```yaml
# WRONG — string 'true' is always truthy
if: 'true'

# CORRECT — boolean true
if: true

# CORRECT — string comparison for values
if: github.ref == 'refs/heads/main'
```

### Pitfall 3: Cache Key Changes with Every Push

```yaml
# WRONG — cache NEVER hits because SHA changes every time
key: build-${{ github.sha }}

# CORRECT — hashFiles captures content identity
key: build-${{ hashFiles('src/**/*.ts') }}
```

### Pitfall 4: No `restore-keys` on First Run

On the very first workflow run for a new repository, no cache exists. Without `restore-keys`, the cache step just skips (no error, no restore). With `restore-keys`, at least there's a chance of a partial match from other workflows.

### Pitfall 5: Artifact Name Collisions

```yaml
# WRONG — all matrix jobs upload to the same artifact name
name: node_modules

# CORRECT — each matrix variant has a unique name
name: node_modules-${{ matrix.node }}
```

### Pitfall 6: Missing Teardown in Integration Tests

```yaml
# WRONG — if tests fail, docker compose is never stopped
- run: docker compose up -d
- run: npm run test:integration   # if this fails → containers leak!
- run: docker compose down        # never runs

# CORRECT — teardown always runs
- run: docker compose up -d
- run: npm run test:integration
- if: always()
  run: docker compose down -v
```

---

## Appendix: Action Version Compatibility

### `actions/cache@v4` Breaking Changes from v3

| Change | v3 | v4 |
|--------|----|----|
| Cache key format | Plain string | Same (no change) |
| Save behavior | Post-action only | Post-action only |
| Sub-actions | N/A (single action) | `restore`, `save`, full |
| Windows paths | Forward slashes | Native backslashes |
| Cache size limit | ~5 GB | ~10 GB |
| Compression | gzip | zstd (faster) |

### `actions/upload-artifact@v4` Breaking Changes from v3

| Change | v3 | v4 |
|--------|----|----|
| Multiple uploads to same name | Merged | Replaced (last wins) |
| Root behavior | Flattened | Preserved |
| Cross-workflow download | Not supported | Supported with `run-id` |
| Storage format | ZIP | ZIP (but faster) |

### `docker/build-push-action@v6` Key Features

- Built-in BuildKit support (no separate `setup-buildx` needed in newer versions, but explicit is better)
- Multiple cache backend support (gha, registry, local, S3, Azure)
- `provenance` and `sbom` attestation support
- Multi-platform builds
- Secrets mounting
- `cache-from` and `cache-to` as first-class inputs

---

## Appendix: The 8-Job DAG Reference

```
                          ┌──────────────────┐
                          │   cache-calc      │  (compute all cache keys)
                          └────────┬─────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
          ┌─────────────────┐ ┌──────────┐ ┌──────────┐
          │  deps-install    │ │ lint     │ │ docker   │
          │ (npm ci + cache) │ │ typecheck│ │ prepare  │
          └────────┬────────┘ └──────────┘ └──────────┘
                   │
                   ▼
          ┌─────────────────┐
          │     build        │
          │ (tsc + vite)     │
          └────────┬─────────┘
                   │
          ┌────────┴────────┐
          ▼                 ▼
   ┌─────────────┐   ┌──────────────┐
   │  test-unit   │   │ test-integ   │
   │ (matrix x10) │   │ (docker)     │
   └─────────────┘   └──────┬───────┘
                            │
                            ▼
                   ┌──────────────────┐
                   │  cache-warm      │  (main only)
                   │  (prime caches   │
                   │   for next build)│
                   └──────────────────┘
```

The DAG shows the execution dependency flow. Jobs at the same horizontal level (e.g., `lint` and `docker-prepare`) run in PARALLEL. Jobs connected by arrows run SEQUENTIALLY (the downstream job waits for the upstream one).

**Total execution timelines (estimated):**

| Stage | Wall-clock time | Parallelism |
|-------|----------------|-------------|
| cache-calc | 15s | 1 runner |
| deps-install | 60-120s | 3 runners (matrix) |
| lint | 30-60s | 1 runner (parallel with docker-prepare) |
| docker-prepare | 60-120s | 1 runner (parallel with lint) |
| build | 60-120s | 3 runners (matrix, after deps-install) |
| test-unit | 120-300s | 10 runners (matrix, after build) |
| test-integration | 180-300s | 1 runner (after build, parallel with test-unit) |
| cache-warm | 60-120s | 1 runner (after tests, main only) |

**Critical path:** cache-calc → deps-install → build → test-unit (or test-integration) → cache-warm

Total estimated minimum wall-clock time: ~5-8 minutes (with full cache hits).

---

> **End of documentation for Workflow 1: Advanced Cache & Build Acceleration.**
>
> Return to [DESIGN.md](../DESIGN.md) for the full lab specification.
