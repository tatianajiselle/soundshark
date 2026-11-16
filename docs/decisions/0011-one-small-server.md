# 0011. Start on one small server

**Status:** Accepted

## Context

The workload is a read-only API with modest traffic and a few batch jobs a day. It needs HTTPS, a schedule, and a place for the raw store. Kubernetes would be interesting to learn, but nothing here needs it yet.

## Decision

- **One Docker image, two commands**: `api` (the explorer) and `jobs` (crawl, ingest, graph). All configuration comes from environment variables.
- It runs on **one small DigitalOcean Droplet** with **Docker Compose**: the API plus Caddy for automatic HTTPS. Cron on the host runs the jobs.
- The raw store lives on an attached **volume**, so it survives rebuilding the server, and is backed up.
- Deploys are manual at first. CI (lint, format, type check, tests) already runs on every push; automated deploys come later.

Each step up has a written trigger:

| Stage | Setup | Move on when |
|---|---|---|
| 0 | Laptop + managed database | jobs need to run reliably on a schedule |
| 1 | One server with Compose + cron | traffic outgrows one instance |
| 2 | Several stateless API instances | many services or hosts to coordinate |
| 3 | Kubernetes: a Deployment for the API, CronJobs for jobs | analytics get heavy enough for a warehouse |

## Consequences

- Cheap, simple, and easy to understand end to end.
- One server is a single point of failure. For a hobby explorer, that's acceptable.
- Moving to Kubernetes later reuses the same image; only the wiring changes.

## Alternatives considered

- **Kubernetes from day one.** A lot of moving parts for one API and a cron job.
- **A serverless platform.** Less to manage, but awkward for long crawls and a local raw store.
