# ADR 0013: CI/CD: tested images on GHCR, one-host Docker Compose deploy over SSH

- Status: accepted (2026-11-01)
- Builds on: ADR 0001 (Postgres job queue, lease recovery), ADR 0009 (spend caps)

## Context

CI already ran the tests, migrations and frontend build on every PR. Nothing built a deployable artifact or
shipped one. The constraints:
- **₹0**: GitHub Actions and GHCR are free for public repositories. The intended host is a free single VM, e.g.
  Oracle Cloud's Always Free Arm machine.
- **ARM and x86**: the free VM is ARM, while most paid hosts are x86.
- **Safety**:
  - migrations run before new code serves traffic
  - a bad release must not stay live
  - jobs survive restarts (already true: leases and SIGTERM release)
- **Simplest thing that works**: one host, no orchestrator.

## Decision

**Packaging.**
- `docker/Dockerfile.backend` builds one image that serves the API, the worker and migrations; compose picks the
  command.
- `docker/Dockerfile.web` holds the built React app behind nginx, which also proxies `/api`, `/health` and
  `/docs`. The browser sees one origin, so no CORS configuration is needed.

**CI** (`.github/workflows/ci.yml`), on every PR and push to `main`:
1. `backend` and `frontend` jobs as before.
2. `images`: native builds on `ubuntu-latest` (amd64) and `ubuntu-24.04-arm` (arm64).
   - It boots the **production compose file** from those images with the stub pipeline (no model, SEC or price
     calls), then runs one research job end to end through nginx (`deploy/ci-smoke.sh`).
   - On `main` it pushes `sha-<12>-<arch>`.
3. `publish` (main only): joins the two into one multi-arch `sha-<12>` tag and `latest`.

**CD** (`.github/workflows/deploy.yml`):
- Triggered when CI succeeds on a push to `main`, or manually with a tag (rollback).
- It runs only when the repository variable `DEPLOY_ENABLED` is `true` and the `production` environment holds
  `DEPLOY_HOST`, `DEPLOY_USER` and `DEPLOY_SSH_KEY` (and optionally `DEPLOY_PATH`).
- It copies `deploy/docker-compose.yml`, `deploy.sh` and `smoke.sh`, then runs `deploy.sh <tag>` on the server:
  1. pull
  2. `migrate` runs to completion (API and worker wait on it)
  3. restart
  4. smoke test
  5. on failure, roll back to the previously deployed tag
- The server's `.env` (from `deploy/.env.example`) is the only place secrets live. It never leaves the host.

## Alternatives

| Option | Why not |
| --- | --- |
| Platform-as-a-service (Render, Railway, Fly) | Free tiers sleep or have no always-on worker; the queue needs one. Paid tiers break the ₹0 constraint |
| Kubernetes / ECS | Orchestration for one host is complexity without a requirement |
| Build on the server from git | Untested artifacts, slow ARM builds, compilers on the host; CI-built images are what the smoke test ran |
| QEMU cross-builds for arm64 | Several times slower than GitHub's free native ARM runners |
| Pull-based deploy (Watchtower) | No migration ordering, no smoke test or rollback, and a long-lived registry credential on the host |

## Failure modes

| Failure | Detection | Handling |
| --- | --- | --- |
| Image broken at runtime (imports, missing files, nginx config) | CI smoke test on both architectures | Never pushed |
| Migration fails on the server | `migrate` exits non-zero; API and worker don't start on the new tag | `deploy.sh` smoke fails → previous tag restarted. The DB is unchanged if the migration's transaction rolled back |
| New code unhealthy after migrating | Smoke test (health, UI, API through nginx) | Roll back to the previous tag. **Migrations must stay backward compatible** (expand, then contract in a later release) for this to be safe |
| Worker killed mid-job by the restart | SIGTERM with a 70s grace period | The job is released without spending an attempt (ADR 0001); another worker resumes it from the last completed stage |
| Bad release found later | Humans | Run Deploy manually with an older `sha-…` tag |
| Two deploys at once | `concurrency: deploy-production` | Queued, never parallel |
| SSH key leaked | GitHub environment secret, scoped to `production` | Rotate the key; it should be a deploy-only user's |

## Consequences

- Every commit on `main` has an immutable, tested image pair; rollback is choosing a tag.
- CI time grows by the image builds (cached through inline cache from `latest`).
- One host is a single point of failure, which is accepted for a demo. Backups (a `pg_dump` cron) are the next ops
  task.
- No authentication yet (STATUS D6): set budget caps, and don't share a public link widely until auth or rate
  limits land.

## When we'd revisit this

- More than one host or zero-downtime needs: a managed container service, blue/green.
- Real users: auth, TLS (Caddy in front of nginx, or a tunnel), backups, monitoring.

## Interview questions

1. *"How do you make sure what you deploy is what you tested?"* CI smoke-tests the exact images it pushes, tagged by
   commit, and the deploy pulls that tag. Nothing is built on the server.
2. *"How do you handle migrations during deploys?"* A one-shot `migrate` service runs before the API and worker
   start. Rollback only swaps code, so migrations must be backward compatible: expand first, contract later.
3. *"What happens to a running research job when you deploy?"* The worker gets SIGTERM, releases its lease without
   burning an attempt, and the new worker resumes from the last completed stage.
4. *"Why not Kubernetes?"* One host, one queue in Postgres. Compose with health checks gives ordering, restarts
   and rollbacks. An orchestrator would add operations work and solve nothing we need yet.
