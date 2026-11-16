# 0007. A four-layer schema

**Status:** Accepted

## Context

Lineups are messy: names are spelled several ways, one line of a bill can hold a b2b, and the same artist turns up across many sources. Matching artists will be wrong at first and will keep improving. Fixing the matching must never require re-crawling, and must never touch what the sources actually said.

## Decision

The schema has four layers, each built only from the one before it:

| Layer | Tables | Holds |
|---|---|---|
| **Provenance** | `crawl_runs`, `raw_pages` | what was fetched, when, and where it is stored |
| **Source facts** | `venues`, `events`, `lineup_slots` | what each source printed, exactly as printed |
| **Identity** | `artists`, `artist_aliases`, `credits` | which real artist or act each line of a bill refers to |
| **Derived** | `artist_edges`, `related_artists` | the graph and the precomputed answers |

A few rules make it work:

- Nobody edits source facts by hand. Corrections happen in the identity layer.
- A lineup slot keeps its raw text, room, position and tags (live, all night long, and so on).
- `is_b2b` is true only when the bill says b2b or vs. "A & B" is treated as one act, a duo, by default.
- Event times are always stored with a time zone.
- Alter egos stay separate artists for now; a link between them can come later.

## Consequences

- The identity layer can be thrown away and rebuilt at any time from source facts.
- Every edge in the graph can be explained, all the way back to a page and a crawl.
- Two layers of derived data must be rebuilt after matching changes. That's what the nightly job is for.

## Alternatives considered

- **Artists stored directly on events.** Simpler at first, but every matching fix becomes a data migration.
- **One wide table per source.** Fast to write, impossible to join across sources.
