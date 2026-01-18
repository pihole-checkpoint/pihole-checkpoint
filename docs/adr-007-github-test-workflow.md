# ADR-007: GitHub Actions Test Workflow Integration

**Status:** Accepted
**Date:** 2026-01-18
**Deciders:** Project Owner

---

## Context

ADR-005 defines the testing strategy and ADR-006 defines the Docker image publishing workflow. We need a GitHub Actions workflow that:

1. Runs tests on pull requests, pushes to main/master, and tag pushes
2. Runs **before** the Docker image is built and published
3. Prevents running tests twice (e.g., on PR merge then again on push to main)
4. Gates Docker publishing on test success

The challenge is coordinating two workflows without:
- Running tests twice when a PR is merged
- Publishing a Docker image if tests fail
- Creating unnecessary complexity

---

## Decision

Implement a two-workflow architecture using GitHub Actions `workflow_run` event to chain test and Docker workflows.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Trigger Events                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Pull Request ──────┐                                                  │
│                      │                                                  │
│   Push to main ──────┼──────► test.yml (runs tests)                    │
│                      │              │                                   │
│   Tag push (v*) ─────┘              │ on completion (success)           │
│                                     ▼                                   │
│                            docker-publish.yml                           │
│                            (builds & publishes)                         │
│                                                                         │
│   workflow_dispatch ───────► docker-publish.yml (manual, skips tests)  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Strategy to Prevent Duplicate Test Runs

Use **pull_request target filtering** combined with **push branch filtering**:

| Event | Condition | Tests Run? | Rationale |
|-------|-----------|------------|-----------|
| `pull_request` | Any PR | ✅ Yes | Validate PR before merge |
| `push` to main/master | Only if NOT from merged PR | ✅ Yes | Direct pushes need testing |
| `push` tags | `v*` tags | ✅ Yes | Validate release |

**Key insight:** Use `github.event.head_commit.message` to detect merge commits and skip redundant test runs on main after a PR merge. Alternatively, use the cleaner `concurrency` groups approach.

### Recommended Approach: Concurrency Groups

Use GitHub's `concurrency` feature to cancel redundant runs:

```yaml
concurrency:
  group: test-${{ github.ref }}
  cancel-in-progress: true
```

This ensures:
- Only one test run per branch/PR at a time
- New pushes cancel in-progress runs on the same branch
- No duplicate runs waste resources

### Workflow Chaining with `workflow_run`

The Docker workflow triggers **after** the test workflow completes successfully:

```yaml
# docker-publish.yml
on:
  workflow_run:
    workflows: ["Tests"]
    types: [completed]
    branches: [main, master]
  push:
    tags:
      - 'v*'
  workflow_dispatch:
    # Manual trigger bypasses test requirement
```

With condition to only run on success:
```yaml
jobs:
  build-and-push:
    if: >
      github.event_name == 'workflow_dispatch' ||
      github.event_name == 'push' ||
      (github.event_name == 'workflow_run' && github.event.workflow_run.conclusion == 'success')
```

---

## Workflow Implementations

### Test Workflow (`.github/workflows/test.yml`)

```yaml
name: Tests

on:
  pull_request:
    branches: [main, master]
  push:
    branches: [main, master]
    tags:
      - 'v*'

concurrency:
  group: test-${{ github.head_ref || github.ref }}
  cancel-in-progress: true

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run tests with coverage
        env:
          SECRET_KEY: 'test-secret-key-for-ci'
          FIELD_ENCRYPTION_KEY: 'test-encryption-key-32char'
        run: |
          pytest --cov=backup --cov-report=xml --cov-report=term-missing

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        if: always()
        with:
          files: ./coverage.xml
          fail_ci_if_error: false

  lint:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install linting tools
        run: pip install ruff

      - name: Run Ruff linter
        run: ruff check .

      - name: Run Ruff formatter check
        run: ruff format --check .
```

### Updated Docker Workflow (`.github/workflows/docker-publish.yml`)

```yaml
name: Build and Publish Docker Image

on:
  # Trigger after test workflow completes on main/master
  workflow_run:
    workflows: ["Tests"]
    types: [completed]
    branches: [main, master]

  # Tag pushes trigger directly (tests run in parallel via test.yml)
  push:
    tags:
      - 'v*'

  # Manual trigger (bypasses tests - use with caution)
  workflow_dispatch:
    inputs:
      tag:
        description: 'Custom image tag (optional)'
        required: false
        type: string
      skip_test_check:
        description: 'Skip test requirement (emergency only)'
        type: boolean
        default: false

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  # Gate job - checks if we should proceed
  check-tests:
    runs-on: ubuntu-latest
    outputs:
      should-build: ${{ steps.check.outputs.should-build }}
    steps:
      - name: Determine if build should proceed
        id: check
        run: |
          if [[ "${{ github.event_name }}" == "workflow_dispatch" ]]; then
            echo "should-build=true" >> $GITHUB_OUTPUT
            echo "Manual trigger - proceeding with build"
          elif [[ "${{ github.event_name }}" == "push" ]]; then
            echo "should-build=true" >> $GITHUB_OUTPUT
            echo "Tag push - proceeding with build"
          elif [[ "${{ github.event.workflow_run.conclusion }}" == "success" ]]; then
            echo "should-build=true" >> $GITHUB_OUTPUT
            echo "Tests passed - proceeding with build"
          else
            echo "should-build=false" >> $GITHUB_OUTPUT
            echo "Tests failed or skipped - aborting build"
          fi

  build-and-push:
    needs: check-tests
    if: needs.check-tests.outputs.should-build == 'true'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
      attestations: write
      id-token: write

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          # For workflow_run, checkout the commit that triggered tests
          ref: ${{ github.event.workflow_run.head_sha || github.sha }}

      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata (tags, labels)
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=raw,value=latest,enable=${{ github.ref == 'refs/heads/main' || github.ref == 'refs/heads/master' || github.event.workflow_run.head_branch == 'main' || github.event.workflow_run.head_branch == 'master' }}
            type=ref,event=branch
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=semver,pattern={{major}}
            type=sha,prefix=sha-
            type=raw,value=${{ inputs.tag }},enable=${{ inputs.tag != '' }}

      - name: Build and push Docker image
        id: push
        uses: docker/build-push-action@v6
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Generate artifact attestation
        uses: actions/attest-build-provenance@v2
        with:
          subject-name: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          subject-digest: ${{ steps.push.outputs.digest }}
          push-to-registry: true
```

---

## Event Flow Scenarios

### Scenario 1: Pull Request

```
Developer creates PR
    │
    ▼
test.yml runs (PR event)
    │
    ▼
PR shows test status ✅/❌
    │
    ▼
(Docker workflow does NOT run - PRs don't publish)
```

### Scenario 2: Merge to Main

```
PR merged to main
    │
    ▼
test.yml runs (push event to main)
    │
    ├── Tests pass ────► docker-publish.yml runs (workflow_run event)
    │                          │
    │                          ▼
    │                    Image published to ghcr.io
    │
    └── Tests fail ────► docker-publish.yml does NOT run
```

### Scenario 3: Tag Release

```
git tag v1.0.0 && git push origin v1.0.0
    │
    ├──────────────────────────────────────┐
    │                                      │
    ▼                                      ▼
test.yml runs                    docker-publish.yml runs
(tag event)                      (tag event - direct trigger)
    │                                      │
    └── If tests fail,                     └── Publishes image
        manual intervention                    with version tags
        needed
```

**Note:** For tag pushes, both workflows run in parallel. The Docker workflow proceeds regardless of test status. To enforce test-gating on tags, use a different approach (see Alternatives).

### Scenario 4: Manual/Emergency Publish

```
Actions > Run workflow (manual trigger)
    │
    ▼
docker-publish.yml runs directly
(bypasses test requirement)
    │
    ▼
Image published with manual-<sha> tag
```

---

## Why Not Single Workflow?

**Alternative considered:** Put tests and Docker build in the same workflow.

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    # ... test steps ...

  build:
    needs: test
    # ... docker steps ...
```

**Rejected because:**
1. Tests would run again on every tag push even if just released
2. Can't easily skip tests for emergency manual deploys
3. Harder to see test status separately from build status
4. PR test results would show "docker" job as skipped, confusing contributors

---

## Alternative: Reusable Workflow

For stricter control, use a reusable workflow:

```yaml
# .github/workflows/ci.yml (main orchestrator)
name: CI/CD

on:
  pull_request:
  push:
    branches: [main, master]
    tags: ['v*']

jobs:
  test:
    uses: ./.github/workflows/test.yml

  docker:
    needs: test
    if: github.event_name == 'push'  # Only on push, not PR
    uses: ./.github/workflows/docker-build.yml
    with:
      push: true
```

This approach:
- ✅ Guarantees tests run before Docker build
- ✅ Single workflow status in PR
- ❌ More complex setup
- ❌ Less flexible for manual triggers

---

## Configuration Checklist

### Required Repository Settings

1. **Branch Protection Rules** (Settings > Branches > Add rule)
   - Branch name pattern: `main` (and/or `master`)
   - ☑️ Require status checks to pass before merging
   - Select required checks: `test`, `lint`
   - ☑️ Require branches to be up to date

2. **Actions Permissions** (Settings > Actions > General)
   - ☑️ Allow all actions and reusable workflows
   - Workflow permissions: Read and write permissions

### Files to Create

| File | Purpose |
|------|---------|
| `.github/workflows/test.yml` | Test and lint workflow |
| `.github/workflows/docker-publish.yml` | Docker build and publish (update existing) |
| `requirements-dev.txt` | Test dependencies (from ADR-005) |
| `pyproject.toml` or `pytest.ini` | Pytest configuration |

---

## Consequences

### Positive

- Tests must pass before Docker images are published to main
- PRs get fast test feedback without waiting for Docker builds
- Clear separation of concerns (test vs build)
- Manual override available for emergencies
- Concurrency groups prevent wasted CI minutes
- Branch protection enforces quality gate

### Negative

- Two workflows to maintain
- `workflow_run` adds slight delay (~10s) between test completion and Docker build start
- Tag releases can publish before tests complete (if desired, this can be changed)
- More complex than single workflow approach

### Mitigations

- Keep workflows simple and well-documented
- Use branch protection as the ultimate gate
- Consider reusable workflow if tighter coupling needed
- Add Slack/Discord notification on failed test-gated deploys

---

## Implementation Order

1. [x] Create `requirements-dev.txt` with test dependencies
2. [x] Create `pyproject.toml` with pytest configuration
3. [x] Create `.github/workflows/test.yml`
4. [x] Create `.github/workflows/docker-publish.yml` with `workflow_run` trigger
5. [ ] Configure branch protection rules
6. [ ] Test with a PR to verify flow
7. [ ] Test tag release flow

---

## References

- [GitHub Actions: workflow_run event](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#workflow_run)
- [GitHub Actions: Concurrency](https://docs.github.com/en/actions/using-jobs/using-concurrency)
- [GitHub: Requiring status checks](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches#require-status-checks-before-merging)
- ADR-005: Testing Strategy
- ADR-006: GitHub Docker Publishing
