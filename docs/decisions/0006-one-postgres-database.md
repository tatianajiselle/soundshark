# 0006. One managed Postgres database

**Status:** Accepted

## Context

The data is small and read-heavy: tens of thousands of artists, a few million artist-to-artist edges at most, written in nightly batches. It needs to be shared between batch jobs and the web API, and possibly several API instances later.

## Decision

A single **Postgres** database, hosted on **Neon** (serverless Postgres), for everything except raw pages.

- Access through **SQLAlchemy 2.0** (async, Core style for bulk upserts) on **asyncpg**.
- Schema changes through **Alembic** migrations.
- Neon **branches** give a production database and a separate development database with the same schema.
- Batch jobs use a direct connection; the API uses the pooled one.
- Other systems' IDs (for example MusicBrainz) are plain columns, added by migration when needed.
- Later, **pgvector** in the same database holds the v2 audio embeddings.

## Consequences

- One system to back up, migrate and reason about.
- Stateless API instances work from day one, since nothing lives in a local file.
- Fuzzy name search can use Postgres's own `unaccent` and `pg_trgm` extensions.
- A serverless database can be slow on the first query after it has been idle. Fine for this traffic.

## Alternatives considered

- **SQLite.** Lovely for one process, but can't be shared across machines.
- **A graph database (Neo4j).** The graph math here runs comfortably in Python on an edge list, and it would be one more system to run. See [0009](0009-graph-in-tables.md).
- **Local Postgres in Docker for development.** Workable, but a database branch is closer to production and one less thing to maintain.
