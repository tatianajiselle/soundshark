# 0004. Fetch once, parse many times

**Status:** Accepted

## Context

Parsers are wrong at first. A room name is missed, a b2b isn't split, a new field turns out to matter. If the only copy of a page is whatever the parser extracted, every fix means crawling the site again, which is slow for us and a cost for the site.

Some listings only show upcoming events, and pages disappear. If a page isn't saved when it is seen, it is gone.

## Decision

Every fetched response is saved to a **raw store** before it is parsed. Parsing always reads from that store, so a parser fix means re-parsing saved pages, with no new requests.

The raw store sits behind a small interface (`get`, `put`, `pages`, `save_run`). The first version is gzipped files on local disk; later it can move to a mounted volume or object storage. Raw pages are **kept out of the database**, which only stores where each page is and what came out of it.

Raw pages are private working data. They are never committed to git or published (see [0012](0012-data-ethics.md)).

## Consequences

- Parser changes are cheap and safe to try.
- Every event can be traced to the exact page and crawl it came from.
- Disk use is tiny: years of lineup pages compress to a few megabytes.
- The raw store needs a backup, because it can't be rebuilt once pages are gone.

## Alternatives considered

- **Parse on the fly and keep only results.** Less storage, but every parser bug costs a re-crawl.
- **Raw pages in Postgres.** One place for everything, but bloats a small managed database with blobs nobody queries.
