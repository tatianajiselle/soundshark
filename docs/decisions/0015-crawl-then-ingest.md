# 0015. Crawl, ingest and identify are separate steps

**Status:** Accepted

## Context

[0004](0004-fetch-once-parse-many.md) keeps every fetched page so it can be parsed again, and [0007](0007-four-layer-schema.md) says each layer of the schema is built only from the one before it, so artist matching can be redone without touching what the sources said. Both only hold if each layer has its own step.

Writes also have to be cheap enough for a whole archive: thousands of events and tens of thousands of lineup slots, sent to a managed database over the internet.

## Decision

Three commands, one per layer:

| Command | Reads | Writes |
|---|---|---|
| `crawl` | websites | the page store, and a crawl run (saved when the run starts and again when it ends, with an error if it stopped early) |
| `ingest` | the page store | **provenance and source facts**: `crawl_runs`, `raw_pages`, `venues`, `events`, `lineup_slots` |
| `identify` | `lineup_slots` | **identity**: `artists`, `artist_aliases`, `credits` |

- The page store keeps **every distinct version** of a page. Fetching the same content again only updates its fetch time; changed content adds a version. `raw_pages` has one row per version, with the crawl run that fetched it and where it is stored, and every event points at the exact version it was parsed from.
- `ingest` parses only the latest version of each page. An event's lineup slots are **replaced only when the lineup changed**, inside the same transaction, so unchanged events keep their slots and credits.
- `identify` credits every slot that has no credits yet. New names get an artist and an automatic alias. `identify --rebuild` forgets every automatic alias and credit and the artists left without an alias, then matches again; **manual aliases, and the artists they point to, are never removed**.
- Writes are batched (many rows per statement) rather than one round trip per row.
- Schema changes go through **Alembic migrations**. Tests that need Postgres run against a dedicated throwaway database (a Neon branch) and are skipped where none is configured.

## Consequences

- Fixing a parser means re-running `ingest`; fixing the matching means `identify --rebuild`. Neither sends a request to any site.
- Running any step twice gives the same database.
- The history of a lineup is kept in the page store and listed in `raw_pages`, and any credit can be traced to a slot, an event, a page version and a crawl.
- Artist ids of automatically matched artists change on a rebuild; anything derived from them is rebuilt afterwards anyway ([0009](0009-graph-in-tables.md)).
- `ingest` re-reads the whole store each time. That is seconds at the current size; it can skip unchanged versions later.

## Alternatives considered

- **Write to the database during the crawl.** One step fewer, but every parser fix would need a re-crawl or a second code path.
- **Match artists inside `ingest`.** Simpler, but then the identity layer can't be rebuilt on its own, and replacing slots would silently drop credits.
- **An ORM unit of work per event.** Simpler code, but one round trip per row is far too slow against a remote database.
