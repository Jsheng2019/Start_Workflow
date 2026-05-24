# Workflow Lab — Design Specification

Two production-grade GitHub Actions workflows demonstrating caching, build acceleration, and precision deployment (刀口能力).

---

## Workflow 1: Advanced Cache & Build Acceleration

**File:** `.github/workflows/advanced-cache-build.yml`

**Trigger:** `push` (main + dev branches), `pull_request` (dev → main), `workflow_dispatch`

### Architecture Overview

Multi-dimensional caching strategy that caches at three independent layers:

| Layer | Key Inputs | Scope | Eviction |
|---|---|---|---|
| **Dependencies** | `package-lock.json` hash, OS, Node version | All jobs using npm/apt | Lockfile change |
| **Build output** | Source file hashes, dependency cache key, tsconfig | Build → Test pipeline | Source or dep change |
| **Docker layers** | `Dockerfile` hash, dep cache key | Container build jobs | Dockerfile or dep change |
| **Test results** | Build output key, test file hashes | PR → main merge | Source change |

### Job Dependency Graph

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
   │ (matrix x4)  │   │ (docker)     │
   └─────────────┘   └──────┬───────┘
                            │
                            ▼
                   ┌──────────────────┐
                   │  cache-warm      │  (main only)
                   │  (prime caches   │
                   │   for next build)│
                   └──────────────────┘
```

### GitHub Actions Used

| Action | Version | Purpose |
|---|---|---|
| `actions/checkout` | `v4` | Check out source |
| `actions/setup-node` | `v4` | Node.js runtime with `cache: npm` |
| `actions/cache` | `v4` | Multi-key caching (deps, build, test) |
| `actions/cache/save` | `v4` | Explicit cache save (warm job) |
| `actions/cache/restore` | `v4` | Explicit cache restore (deps job) |
| `actions/upload-artifact` | `v4` | Upload build output between jobs |
| `actions/download-artifact` | `v4` | Download build output |
| `docker/login-action` | `v3` | Docker registry login |
| `docker/metadata-action` | `v5` | Docker image metadata + tags |
| `docker/build-push-action` | `v6` | Build and cache Docker layers |
| `dorny/test-reporter` | `v1` | Test result reporting (PR comments) |

### Job Details

#### 1. `cache-calc`
- **Runs on:** `ubuntu-latest`
- **Purpose:** Single source of truth for all cache keys. Every downstream job reads keys via artifact or summary.
- **Outputs:** `dep-key`, `build-key`, `docker-key`, `test-key`
- **Key computation:**
  - `dep-key`: `npm-cache-${{ hashFiles('package-lock.json') }}-${{ runner.os }}-${{ matrix.node }}`
  - `build-key`: `build-${{ hashFiles('src/**/*.ts', 'tsconfig.json') }}-${{ needs.cache-calc.outputs.dep-key }}`
  - `docker-key`: `docker-${{ hashFiles('Dockerfile', '.dockerignore') }}-${{ needs.cache-calc.outputs.dep-key }}`
- **Restore keys** (fallback): prefix-based partial matches for when exact key misses

#### 2. `deps-install`
- **Runs on:** `matrix` (ubuntu-latest, node: [18, 20, 22])
- **Purpose:** Install npm dependencies with cache. Serves as the foundation for all downstream jobs.
- **Cache strategy:**
  1. `restore` with `dep-key` → if miss, try `restore-keys: npm-cache-${{ runner.os }}-, npm-cache-`
  2. Run `npm ci --prefer-offline`
  3. `save` with `dep-key` (only if cache miss)
- **Output:** `node_modules/` uploaded as artifact for downstream jobs

#### 3. `lint`
- **Runs on:** `ubuntu-latest`, node: 20
- **Needs:** `deps-install`
- **Purpose:** Fastest-feedback job — lint + typecheck
- **Steps:**
  1. Restore deps from `deps-install` artifact
  2. Run `npm run lint`
  3. Run `tsc --noEmit`
  4. Report results via `dorny/test-reporter`

#### 4. `docker-prepare`
- **Runs on:** `ubuntu-latest`
- **Needs:** `cache-calc` (reads docker-key)
- **Purpose:** Pre-build Docker layers for cache warming, runs in parallel with lint
- **Steps:**
  1. Docker layer cache: `docker/build-push-action` with `cache-from` + `cache-to` pointing to GitHub Cache or registry
  2. Uses `docker/metadata-action` for tags/labels

#### 5. `build`
- **Runs on:** `matrix` (node: [18, 20, 22])
- **Needs:** `deps-install`
- **Purpose:** TypeScript compilation + Vite/Rollup bundling
- **Cache strategy:** Restore previous build output via `build-key`. Only rebuild changed files (Webpack/Vite persistent cache).
- **Output:** `dist/` uploaded as artifact

#### 6. `test-unit`
- **Runs on:** `matrix` (node: [18, 20, 22], os: [ubuntu-latest, windows-latest])
- **Needs:** `build`
- **Purpose:** Unit tests split across 4x matrix for parallel execution
- **Cache strategy:** Restore build output, no need to rebuild
- **Steps:**
  1. Download `dist/` from build
  2. Run `npm test -- --shard=${{ matrix.shard }}/${{ strategy.job-total }}`
  3. Upload test reports (JUnit format)

#### 7. `test-integration`
- **Runs on:** `ubuntu-latest`
- **Needs:** `build`
- **Purpose:** Integration tests against Docker Compose environment
- **Steps:**
  1. Download `dist/` artifact
  2. Start containers via Docker Compose
  3. Run integration test suite
  4. Collect container logs on failure
  5. Teardown

#### 8. `cache-warm` (main branch only)
- **Runs on:** `ubuntu-latest`
- **Condition:** `github.ref == 'refs/heads/main'`
- **Needs:** `test-unit`, `test-integration`
- **Purpose:** Prime all cache layers after a successful main build so PRs benefit from warm caches
- **Actions:** Explicitly calls `actions/cache/save` for dep, build, and Docker layer caches

### Key Design Decisions

1. **Cache key chaining:** Build keys include dep-key as input — when deps change, build cache is automatically invalidated. No stale cache problem.
2. **Explicit cache-save vs. post-action:** Using `actions/cache/save` on the `cache-warm` job ensures the main branch always has fresh caches. The built-in post-action save is used as fallback.
3. **Matrix with sharding for test-unit:** Rather than one monolithic test job, tests are sharded by file across 4 parallel runners. Total wall-clock time for tests becomes `max(shard_time)`, not `sum(test_times)`.
4. **Separate cache-calc job:** Centralizing key computation avoids drift between jobs computing the same key differently. Downstream jobs read deterministic output.
5. **Artifact pass-through for node_modules/dist:** Cheaper than having every job restore from cache independently. Cache is for cold-start (first CI run on a branch), artifacts are for subsequent jobs within the same run.

---

## Workflow 2: Precision Deployment & Critical Operations (刀口能力)

**File:** `.github/workflows/precision-deploy.yml`

**Trigger:** `workflow_dispatch` (with input parameters), `release` (published)

### Architecture Overview

A canary deployment pipeline with integrated security verification, SBOM generation, SLSA provenance, and automated rollback. Every deployment is: scanned before building, signed before shipping, verified after deploying, and recoverable if it fails.

```
        ┌──────────────┐
        │  dispatch     │  (manual or release trigger)
        └──────┬───────┘
               │
               ▼
        ┌──────────────┐
        │ security-scan │  (SAST + deps + container scan)
        └──────┬───────┘
               │
               ├─────────────────────┐
               ▼                     ▼
        ┌──────────────┐    ┌──────────────┐
        │ sbom-generate │    │ build-sign   │
        │ (SPDX + sign) │    │ (sign + att) │
        └──────┬───────┘    └──────┬───────┘
               │                    │
               └────────┬──────────┘
                        ▼
                 ┌──────────────┐
                 │ slsa-proven  │  (provenance attestation)
                 └──────┬───────┘
                        │
                        ▼
                 ┌──────────────┐
                 │ deploy-canary│  (5% traffic)
                 └──────┬───────┘
                        │
                        ▼
                 ┌──────────────┐
                 │ smoke-test   │  (verification probes)
                 └──────┬───────┘
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
      ┌──────────────┐   ┌──────────────┐
      │ deploy-prod  │   │ rollback     │
      │ (100% + tag) │   │ (revert +    │
      │              │   │  notify)     │
      └──────────────┘   └──────────────┘
              │
              ▼
     ┌─────────────────┐
     │ post-deploy-ver │  (prod smoke + metric check)
     └─────────────────┘
```

### GitHub Actions Used

| Action | Version | Purpose |
|---|---|---|
| `actions/checkout` | `v4` | Check out source |
| `actions/setup-node` | `v4` | Node.js for build |
| `actions/configure-pages` | `v5` | GitHub Pages config (example target) |
| `actions/upload-artifact` | `v4` | Pass artifacts between jobs |
| `actions/download-artifact` | `v4` | Receive artifacts |
| `actions/attest-build-provenance` | `v1` | SLSA provenance attestation |
| `aquasecurity/trivy-action` | latest | Container + filesystem vulnerability scan |
| `github/codeql-action/upload-sarif` | `v3` | Upload SARIF results to GH |
| `anchore/sbom-action` | `v0` | SPDX SBOM generation |
| `sigstore/cosign-installer` | `v3` | Cosign for artifact signing |
| `slsa-framework/slsa-github-generator` | `v2` | SLSA provenance generation |
| `ncipollo/release-action` | `v1` | GitHub Release management |
| `softprops/action-gh-release` | `v2` | Release artifact upload |
| `nicklasfrahm/rollback-action` | custom | Rollback logic (or manual impl) |
| `slackapi/slack-github-action` | `v2` | Deployment notifications |

### Input Parameters

```yaml
inputs:
  environment:
    description: 'Target environment'
    required: false
    default: 'canary'
    type: choice
    options:
      - canary
      - production
  canary-percent:
    description: 'Canary traffic percentage'
    required: false
    default: '5'
    type: string
  skip-scan:
    description: 'Skip security scan (emergency use only)'
    required: false
    default: false
    type: boolean
  force-rollback:
    description: 'Force rollback to previous version'
    required: false
    default: false
    type: boolean
```

### Job Details

#### 1. `security-scan`
- **Runs on:** `ubuntu-latest`
- **Purpose:** Multi-layered security scan before any build or deployment. Acts as a gating step — if any critical vulnerability is found, the workflow fails fast.
- **Steps:**
  1. **Trivy filesystem scan:** Scans source code for IaC misconfigurations, secrets, and vulnerable libraries
     - `trivy fs --severity CRITICAL,HIGH --exit-code 1 .` — exits 1 on criticals
  2. **Trivy repo scan:** Scans git history for secrets
     - `trivy repo --scanners secret .`
  3. **CodeQL analysis** (via `github/codeql-action`):
     - Initializes CodeQL, runs `autobuild`, performs analysis
     - Uploads SARIF to GitHub Security tab
  4. **Output:** Security report artifact, check run result

#### 2. `sbom-generate`
- **Runs on:** `ubuntu-latest`
- **Needs:** `security-scan`
- **Purpose:** Generates an SPDX 2.3 SBOM for the release, then signs the SBOM with Cosign.
- **Steps:**
  1. Run `anchore/sbom-action` to generate `sbom.spdx.json`
  2. Install Cosign via `sigstore/cosign-installer`
  3. Sign SBOM: `cosign attest-blob sbom.spdx.json --sign`
  4. Upload SBOM + signature as artifact for release attachment

#### 3. `build-sign`
- **Runs on:** `ubuntu-latest`
- **Needs:** `security-scan`
- **Purpose:** Build the deployable artifact + sign it. Parallel with `sbom-generate`.
- **Steps:**
  1. Build Docker image (or Node.js package)
  2. Push to container registry with digest pinning
  3. Sign the image with Cosign: `cosign sign <image>`
  4. Output digest + tag as job outputs

#### 4. `slsa-provenance`
- **Runs on:** `ubuntu-latest` (delegates to `slsa-github-generator` which runs on `ubuntu-latest`)
- **Needs:** `sbom-generate`, `build-sign`
- **Purpose:** Generate SLSA Build Level 2 provenance attestation — cryptographic proof that the artifact was built from this repo, by this workflow.
- **Steps:**
  1. Call `slsa-framework/slsa-github-generator` reusable workflow
  2. Upload generated provenance attestation to release artifacts

#### 5. `deploy-canary`
- **Runs on:** `ubuntu-latest`
- **Needs:** `slsa-provenance`
- **Environment:** `canary` (with protection rules — canary branch must pass CI)
- **Purpose:** Deploy the verified artifact to a canary environment (e.g., 5% of traffic, or isolated staging instance).
- **Steps:**
  1. Pull the signed artifact from registry (verify signature)
  2. Deploy to canary target (k8s manifest update, server push, etc.)
  3. Record the current version as "previous" for rollback
  4. Label the deployment with canary metadata
- **Output:** Target URL for smoke testing, previous version tag

#### 6. `smoke-test`
- **Runs on:** `ubuntu-latest`
- **Needs:** `deploy-canary`
- **Purpose:** Verify the canary deployment is healthy before proceeding. This is the decision point — failure triggers rollback, success triggers production promotion.
- **Steps:**
  1. **Health endpoint:** `GET /health` must return 200 within 30s
  2. **Smoke probes:**
     - Write a record, read it back
     - Verify expected response shape
     - Check error rate < 0.1%
  3. **Latency check:** p95 latency < threshold (e.g., 500ms)
  4. **Graceful degradation:** Disable one dependency, verify fallback behavior
- **Output:** Pass/fail with details

#### 7. `deploy-production`
- **Runs on:** `ubuntu-latest`
- **Needs:** `smoke-test`
- **Environment:** `production`
  - **Required reviewers:** 1 (deploy gate)
  - **Wait timer:** 5 minutes (cool-down for monitoring)
- **Purpose:** Promote canary to 100% traffic. Creates a GitHub Release with all artifacts.
- **Steps:**
  1. Promote canary to production (traffic shift 5% → 100%, or k8s label update)
  2. Attach SBOM + provenance to release
  3. Tag release with semantic version from `package.json`
  4. Send Slack notification

#### 8. `post-deploy-verify`
- **Runs on:** `ubuntu-latest`
- **Needs:** `deploy-production`
- **Purpose:** Deep verification after full rollout, monitoring for 5 minutes.
- **Steps:**
  1. Run full smoke test suite against production
  2. Monitor error budget for 5 minutes
  3. If error rate spikes → notify on-call (don't auto-rollback production unless 5xx > 5%)

#### 9. `rollback`
- **Runs on:** `ubuntu-latest`
- **Condition:** `always()` — but only triggered when:
  - `smoke-test` fails after canary
  - `post-deploy-verify` detects critical degradation
  - `force-rollback` input is true
- **Purpose:** Revert to the previous known-good version that was recorded before deployment.
- **Steps:**
  1. Fetch previously recorded "last-good" version from deploy step
  2. Redeploy that version
  3. Verify rollback succeeded (smoke test the old version)
  4. Send notification and create incident issue

#### 10. `notify` (helper, not shown in graph)
- **Runs on:** `ubuntu-latest`
- **Condition:** `always()`
- **Needs:** all terminal jobs (`deploy-production`, `rollback`)
- **Purpose:** Unified notification about workflow outcome.
- **Steps:**
  1. Aggregate result from all terminal jobs
  2. Send Slack message with: version, environment, result, duration, commit SHA, links to artifacts

### Key Design Decisions

1. **Canary as a gating step, not a parallel branch:** The canary deployment is mandatory — even "direct to production" goes through canary first (minimum 1% traffic). This guarantees the deployment path is tested before full rollout.

2. **SBOM generation BEFORE build-sign:** SBOM describes the source and dependencies. Build-sign produces the binary artifact. Keeping them sequential avoids circular dependencies where the SBOM is needed to sign the build but the build produces the SBOM. In practice, `sbom-generate` and `build-sign` run in parallel after `security-scan`.

3. **SLSA provenance via reusable workflow:** `slsa-framework/slsa-github-generator` is a reusable workflow that generates attestations using GitHub's OIDC identity. This gives Build Level 2+ provenance without managing signing keys. The attestation proves *this specific workflow run* produced *this specific artifact*.

4. **Environment protection rules as the approval gate:** Rather than a custom approval job with `issue_comment` triggers, use GitHub Environments: set `required_reviewers: 1` on the `production` environment. This gives built-in deployment protection with an audit trail.

5. **Rollback with artifact, not git revert:** Rolling back deploys the previous artifact, not a `git revert`. The "previous" artifact is known (its digest was recorded). This avoids deploying unintended changes that have since been merged to main.

6. **Vulnerability scan before any build:** `security-scan` gates everything. If a critical CVE is found, no artifact is built and no signature is generated. This avoids the scenario where a signed, provenance-tracked artifact has known vulnerabilities. The `skip-scan` override exists for emergency hotfixes.

---

## File Structure

```
.github/
  workflows/
    advanced-cache-build.yml     # Workflow 1 (backlog/manual)
    precision-deploy.yml         # Workflow 2 (backlog/manual)
  workflow-lab/
    DESIGN.md                    # This file
```

Both workflow YAML files are to be placed in `.github/workflows/` and will appear in the GitHub Actions UI automatically.

---

## Next Steps for the Backend-Engineer

1. Create `.github/workflows/advanced-cache-build.yml` with all 8 jobs
2. Create `.github/workflows/precision-deploy.yml` with all 10 jobs
3. Verify syntax with `act --dry-run` or push to a feature branch to test
4. Open PR against `main` for review
