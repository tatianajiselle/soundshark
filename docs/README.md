# SoundShark design notes

## Intent

SoundShark maps a music scene by **who plays with whom**. Club lineups are a quiet record of taste: DJs who share a bill, a room or a b2b set usually share a sound, a crew or a city. Collect enough of those nights and a picture appears, of scenes, of bridges between them, and of the DJs closest to any DJ you already love.

SoundShark crawls public lineup history into that graph and answers two questions:

- **Who is related to this DJ?**
- **How are these two DJs connected?**

Later (v2) it listens too, comparing what tracks sound like, not just who played them.

It is built in the open, slowly and on purpose, as a way to learn async Python properly: concurrency, politeness, failure handling, and the plumbing around a real crawler. These notes record the choices made along the way and why, so they can be questioned later instead of rediscovered.

## How to read the decisions

Each decision is short and has the same parts:

- **Status**: accepted, proposed or replaced
- **Context**: the problem and what pushed on it
- **Decision**: what we chose
- **Consequences**: what gets easier, what gets harder
- **Alternatives considered**: what we didn't choose, and why

A decision is never edited to say something new. If it changes, a new decision replaces it and the old one is marked replaced.

## Decisions

| # | Decision | Status |
|---|---|---|
| [0001](decisions/0001-open-engine-private-adapters.md) | Open engine, private site adapters | Accepted |
| [0002](decisions/0002-engine-fetches-sources-parse.md) | The engine fetches; sources only parse | Accepted |
| [0003](decisions/0003-polite-crawling.md) | Crawl politely by default | Accepted |
| [0004](decisions/0004-fetch-once-parse-many.md) | Fetch once, parse many times | Accepted |
| [0005](decisions/0005-idempotent-incremental-crawls.md) | Idempotent, incremental crawls | Accepted |
| [0006](decisions/0006-one-postgres-database.md) | One managed Postgres database | Accepted |
| [0007](decisions/0007-four-layer-schema.md) | A four-layer schema | Accepted |
| [0008](decisions/0008-artist-identity.md) | Artist names: exact matches merge, fuzzy matches wait for a human | Accepted |
| [0009](decisions/0009-graph-in-tables.md) | The graph is tables, computed nightly | Amended by 0018 |
| [0010](decisions/0010-read-only-explorer.md) | A public, read-only explorer with no accounts | Accepted |
| [0011](decisions/0011-one-small-server.md) | Start on one small server | Accepted |
| [0012](decisions/0012-data-ethics.md) | Data ethics: show connections, never copies | Accepted |
| [0013](decisions/0013-layout-and-names.md) | Code is grouped by role, and names say what things do | Accepted |
| [0014](decisions/0014-structured-logging.md) | Structured logging: named events with context | Accepted |
| [0015](decisions/0015-crawl-then-ingest.md) | Crawl, ingest and identify are separate steps | Accepted |
| [0016](decisions/0016-configuration-from-environment.md) | Configuration comes from environment variables, read directly | Accepted |
| [0017](decisions/0017-stop-when-a-site-pushes-back.md) | Stop when a site pushes back | Accepted |
| [0018](decisions/0018-relatedness-scoring.md) | Relatedness: weighted nights, personalized PageRank, top 50 | Accepted |
| [0019](decisions/0019-presents-lines.md) | "X presents Y" credits X | Accepted |
| [0021](decisions/0021-container-image.md) | An engine image here, the deployed image built privately | Accepted |
| [0023](decisions/0023-crawler-stays-on-host.md) | The crawler stays on the host it was sent to | Accepted |

## Decided but not built yet

- **Possibly ambiguous names** ([0008](decisions/0008-artist-identity.md)): very short or very common names should be flagged, to be scoped by city later.
- **Fuzzy merge suggestions in the database** ([0008](decisions/0008-artist-identity.md)): the scoring exists; the review command, and remembering rejected pairs, don't yet.
- **Paths between two artists** ([0009](decisions/0009-graph-in-tables.md)): "how are A and B connected?" as a breadth-first search over `artist_edges`.
- **Scene detection** (roadmap): grouping artists into scenes from the same graph.
- **Conditional requests** ([0005](decisions/0005-idempotent-incremental-crawls.md)): `If-Modified-Since` for feeds.
