# SoundShark 🦈

Map a music scene. **SoundShark** crawls DJ lineups (past and upcoming) into a graph of who plays with whom, then listens to the music to find who really sounds alike.

> Work in progress, built in the open as a way to learn async Python properly.

## Roadmap

### v1: the lineup graph
- Async crawler that expands outward from seed DJs through shared lineups
- Relatedness that rewards b2b sets and recent shows, normalized so big headliners don't connect everyone
- "Who's closest to this DJ's world?" (personalized PageRank) and automatic scene detection

### v2: the sound graph
- Audio features and embeddings from legally sourced previews (BPM, key, style, vibe)
- Vector search for similar-sounding tracks, plus "find me *dark rolling techno with acid*"
- A hybrid recommender: sound similarity + set co-occurrence + lineup graph

## Starting seeds

San Francisco: Claudio PRC, DVS1, Lindsey Herbert, Fadi Mohem, Isabel Soto

## Architecture

The crawl engine (`services/crawler.py`) does all the fetching: a concurrent breadth-first crawl that never fetches a URL twice and returns on its own when there's nothing left to fetch. Talking to websites is split out into `clients/`: `PoliteHttpClient` paces requests per host and retries timeouts, 429s and 5xx with backoff and `Retry-After`; `RobotsRules` always obeys robots.txt, including `Crawl-delay`.

A data source is a small plugin that implements `interfaces/source.py`: its `seed_urls`, its `crawl_policy`, `parse(page)` that turns a fetched page into events and links to follow, and `refetch_after(url)` that says when a stored copy is too old.

```
src/soundshark/
  models/       data only: Event, Page, ParsedPage, CrawlPolicy, CrawlRun
  interfaces/   what the engine depends on: Source, PageStore
  clients/      talking to websites: PoliteHttpClient, RobotsRules
  services/     the logic: crawler, ingest, credits, artist_identity
  stores/       PageStore implementations: FilePageStore
  db/           Postgres tables and connections (migrations live in migrations/)
  sources/      the demo source and the loader for real ones
  utils/        URL helpers and logging setup
```

Logs are structured events (`crawl.started`, `http.retrying`, `page.blocked_by_robots`, `crawl.finished`, ...), each tagged with the source and run id. `-v` adds a line per request and page, `--log-json` prints one JSON object per line.

This repo ships only the interface and a **demo source with fictional data**. Site-specific adapters aren't published: they're loaded at runtime from your own package via `SOUNDSHARK_SOURCES`, a comma-separated list of `module.path:ClassName` (copy `.env.example` to `.env`; it defaults to the demo source).

Crawling, loading and matching are separate steps. `crawl` saves every fetched page under `data/` (ignored by git), keeping each version of a page that changes. `ingest` parses the saved pages again and upserts what the sources said into Postgres. `identify` matches every lineup slot to artists. A parser fix never needs a re-crawl, a matching fix never needs a re-ingest, and running any step twice gives the same database.

```sh
uv run python -m soundshark crawl              # fetch pages into data/ (demo source by default)
uv run python -m soundshark crawl -v           # plus a log line per request and page
uv run alembic upgrade head                    # create or update the tables in DATABASE_URL
uv run python -m soundshark ingest             # data/ into Postgres
uv run python -m soundshark identify           # credit new lineup slots to artists
uv run python -m soundshark identify --rebuild # redo all automatic matching; manual aliases are kept
```

The schema has four layers (provenance, source facts, identity, derived): see [decision 0007](docs/decisions/0007-four-layer-schema.md).

## Design notes

Why SoundShark is built the way it is: [docs/](docs/README.md).

## Development

Uses [uv](https://docs.astral.sh/uv/). It installs the right Python and every dependency from the lockfile.

```sh
uv sync                 # create .venv and install everything
uv run pytest           # tests
uv run ruff check .     # lint
uv run ruff format .    # format
uv run pyright          # type check (also catches un-awaited coroutines)
```

Postgres tests run against `TEST_DATABASE_URL` (a throwaway database or Neon branch: they drop and recreate every table) and are skipped when it isn't set, as in CI. `DATABASE_URL` is a direct connection for migrations and jobs; `DATABASE_URL_POOLED` is for the API later.

CI runs the same checks on every push and pull request.

## Data & ethics

SoundShark only uses data sources whose terms allow it, respects rate limits and robots.txt, and stores audio *features*, never audio.

## License

MIT. See [LICENSE](LICENSE).
