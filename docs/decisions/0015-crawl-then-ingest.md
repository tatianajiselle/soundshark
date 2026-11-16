# 0015. Crawl and ingest are separate steps

**Status:** Accepted

## Context

[0004](0004-fetch-once-parse-many.md) keeps every fetched page so it can be parsed again. That only pays off if loading the database works from the stored pages, not from whatever a crawl happened to return in memory.

Writes also have to be cheap enough for a whole archive: thousands of events and tens of thousands of lineup slots, sent to a managed database over the internet.

## Decision

- **`crawl`** fetches pages into the page store and records the run. It never touches the database.
- **`ingest`** reads every stored page, parses it with the source's current parser, and upserts the results into Postgres in batches, one transaction per batch: raw page metadata, venues, events, lineup slots, then artists, aliases and credits.
- An event's lineup slots are **replaced** whenever it is ingested, inside the same transaction, so a changed lineup never leaves stale rows behind.
- New names get an artist and an automatic alias. Existing aliases, and every **manual** alias, are never overwritten.
- Writes are batched (many rows per statement) rather than one round trip per row.
- Schema changes go through **Alembic migrations**. Tests that need Postgres run against a dedicated throwaway database (a Neon branch) and are skipped where none is configured.

## Consequences

- Fixing a parser means re-running `ingest`, with no new requests to any site.
- Running `ingest` twice gives the same database.
- The two steps can run on different schedules, and on different machines.
- Ingest re-parses the whole store each time. That is seconds for the current archive size; it can be made incremental later by skipping pages whose content hash hasn't changed.

## Alternatives considered

- **Write to the database during the crawl.** One step fewer, but every parser fix would need a re-crawl or a second code path.
- **An ORM unit of work per event.** Simpler code, but one round trip per row is far too slow against a remote database.
