# 0021. An engine image here, the deployed image built privately

**Status:** Accepted. Fills in [0011](0011-one-small-server.md) for the jobs; the `api` command arrives with the explorer.

## Context

[0011](0011-one-small-server.md) settled on one Docker image run by Compose and cron on one server. [0001](0001-open-engine-private-adapters.md) keeps the site adapters private and says deploys are built from the private side. The public repo still needs an image that anyone can build and run with the demo source.

## Decision

- **The public repo builds the engine image.** A `Dockerfile` installs the locked runtime dependencies with uv in a build stage, then copies only the virtual environment, `alembic.ini` and `migrations/` into a slim Python image. It runs as a non-root user, and its entrypoint is `soundshark`.
- **The private repo builds the deployed image** the same way, from its own checkout plus the engine checkout (a named build context), synced from the private lockfile. One lockfile then pins everything in the deployed image, the engine's dependencies included. The public image never contains an adapter.
- **`soundshark jobs`** runs crawl, ingest, identify and graph in that order, and stops at the first step that fails, so a broken crawl never feeds a half-updated graph.
- **Migrations are a separate, explicit step** (`alembic upgrade head`, the `migrate` service in Compose), run on deploy rather than before every job.
- **The page store is a volume** at `/app/data`. On the server it maps to the attached volume from [0011](0011-one-small-server.md).
- **Cron on the host** runs `docker compose run --rm jobs` once a night. Each run is a fresh container that exits when the work is done.
- **CI builds the image** on every push and runs it once, so the `Dockerfile` can't quietly break.

## Consequences

- The public repo stays runnable end to end with the demo source: `docker compose --profile jobs run --rm jobs`.
- Updating the engine means pulling both checkouts and rebuilding; when the engine's dependencies change, the private lockfile is refreshed too.
- Settings still come only from environment variables ([0016](0016-configuration-from-environment.md)); Compose reads them from `.env`, which never goes into either image.

## Alternatives considered

- **One image built in the private repo only.** Simpler, but nobody else could run the open engine in a container.
- **Build the private image `FROM` the engine image.** Reuses the engine image, but the adapters' dependencies would be installed on top of versions pinned by a different lockfile.
- **A scheduler inside a long-running container** (cron or supercronic in Compose). Self-contained, but adds a process to watch; the host already has cron.
- **Run migrations at the start of every job.** Fewer steps to remember, but a bad migration would then run unattended at night.
