# 0005. Idempotent, incremental crawls

**Status:** Accepted

## Context

Crawls run on a schedule and will sometimes fail halfway, get re-run by hand, or overlap with a fix. Most pages never change: last year's lineups are history.

## Decision

- **Idempotent writes.** Every event is keyed by `(source, source_id)` and written with an upsert. Running the same job twice gives the same database.
- **Incremental crawls.** Each source says how long a page stays fresh. Archive pages for the past are never fetched again; current and upcoming pages are refreshed about once a day. Feeds use conditional requests (`If-Modified-Since`) where the server supports them.
- **Every run is recorded** as a crawl run: when it started and finished, how many pages were fetched, served from the store, or failed, and how many events came out.

## Consequences

- Re-running a job is always safe, which makes failures boring.
- Routine crawls fetch a handful of pages instead of a whole archive.
- Crawl runs double as monitoring: a run with zero events or many failures is easy to spot.
- When a lineup changes, the event's slots are replaced in one transaction; the history stays in the raw store.

## Alternatives considered

- **Full re-crawls every time.** Simpler logic, many times the traffic.
- **Append-only events with deduplication later.** Harder to query and easy to get wrong.
