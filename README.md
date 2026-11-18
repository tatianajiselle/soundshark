# SoundShark 🦈

Map a music scene. **SoundShark** crawls DJ lineups (past and upcoming) into a graph of who plays with whom, then listens to the music to find who really sounds alike.

> Work in progress...

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

The crawl engine (`services/crawler.py`) does all the fetching: a concurrent breadth-first crawl that never fetches a URL twice and returns on its own when there's nothing left to fetch. Talking to websites is split out into `clients/`: `PoliteHttpClient` paces requests per host and retries timeouts, 429s and 5xx with backoff and `Retry-After`; `RobotsRules` always obeys robots.txt, including `Crawl-delay`. A 401, 403 or 451, or five timeouts, 429s or server errors in a row, stops the whole crawl ([decision 0017](docs/decisions/0017-stop-when-a-site-pushes-back.md)).

A data source is a small plugin that implements `interfaces/source.py`: its `seed_urls`, its `crawl_policy`, `parse(page)` that turns a fetched page into events and links to follow, and `refetch_after(url)` that says when a stored copy is too old.

```
src/soundshark/
  models/       data only: Event, Page, ParsedPage, CrawlPolicy, CrawlRun, GraphScoring, SceneSettings
  interfaces/   what the engine depends on: Source, PageStore
  clients/      talking to websites: PoliteHttpClient, RobotsRules
  services/     the logic: crawler, ingest, credits, artist_identity, artist_graph, graph_job, related_lookup, scenes, scene_job, map_export, graph_evaluation, ranking_changes, scoring_variants
  stores/       PageStore implementations: FilePageStore
  db/           Postgres tables and connections (migrations live in migrations/)
  sources/      the demo source and the loader for real ones
  utils/        URL helpers and logging setup
```

Logs are structured events (`crawl.started`, `http.retrying`, `page.blocked_by_robots`, `crawl.finished`, ...), each tagged with the source and run id. `-v` adds a line per request and page, `--log-json` prints one JSON object per line.

This repo ships only the interface and a **demo source with fictional data**. Site-specific adapters aren't published: they're loaded at runtime from your own package via `SOUNDSHARK_SOURCES`, a comma-separated list of `module.path:ClassName` (copy `.env.example` to `.env`; it defaults to the demo source).

Crawling, loading and matching are separate steps. `crawl` saves every fetched page under `data/` (ignored by git), keeping each version of a page that changes. `ingest` parses the saved pages again and upserts what the sources said into Postgres. `identify` matches every lineup slot to artists. A parser fix never needs a re-crawl, a matching fix never needs a re-ingest, and running any step twice gives the same database.

```sh
uv run soundshark crawl               # fetch pages into data/ (demo source by default)
uv run soundshark crawl -v            # plus a log line per request and page
uv run alembic upgrade head           # create or update the tables in DATABASE_URL
uv run soundshark ingest              # data/ into Postgres
uv run soundshark identify            # credit new lineup slots to artists
uv run soundshark identify --rebuild  # redo all automatic matching; manual aliases are kept
uv run soundshark graph               # rebuild artist edges and the top 50 related artists
uv run soundshark related "Ora Vance" # who is closest, and why
uv run soundshark scenes              # group artists into scenes; ids carry over from the last run
uv run soundshark export-map          # write data/map/map.json and map.json.gz for the explorer
uv run soundshark evaluate            # backtest rankings against later same-room nights
uv run soundshark evaluate --variant "flat:room_profile_floor=1.0" --cutoff 2025-01-01
uv run soundshark movers --set room_profile_floor=1.0  # whose top 10 changes most
```

`evaluate` and `movers` compare scoring settings before you change the defaults: see [decision 0020](docs/decisions/0020-checking-the-graph.md).

`scenes` clusters each artist's top 10 related artists into scenes, labelled by their three most-booked members, and keeps last night's scene ids where the members mostly match ([decision 0024](docs/decisions/0024-scenes.md)). `export-map` writes the public map file: artists, scenes and scores only, never dates, rooms, venues or lineups ([decision 0025](docs/decisions/0025-the-map-file.md)). `--out` picks another path.

The schema has four layers (provenance, source facts, identity, derived): see [decision 0007](docs/decisions/0007-four-layer-schema.md).

## Explorer

`explorer/` is a static web app that draws the related-artists graph from one file, `map.json`: the whole map coloured by scene, an artist's neighbourhood up to three hops, and the shortest path between two artists ([decision 0026](docs/decisions/0026-the-explorer.md)). It needs Node 22.

```sh
cd explorer
npm ci
npm run fake-map    # write an invented map to public/map.json (--artists 30000 for a big one)
npm run dev         # http://localhost:5173
npm run build       # the app in dist/, served with map.json next to it
npm run typecheck && npm run lint && npm test
npm run e2e         # build, then Playwright in headless Chromium
```

The fake map is made-up names with planted scenes; a real `map.json` is never committed. In production the built app is served at `/` and the engine's `map.json` at `/map.json`. The page loads nothing from other hosts. It needs this Content-Security-Policy: `default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`.

The graph is drawn with [Cosmograph](https://cosmograph.app/), which is licensed [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) (free for non-commercial use, with credit). The rest of the explorer is MIT, like the engine.

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

Postgres tests run against `TEST_DATABASE_URL` (a throwaway database or Neon branch: they drop and recreate every table) and are skipped when it isn't set, as in CI. `DATABASE_URL` is the connection the jobs use. In production it's a limited role made with `soundshark create-jobs-role`, which needs the owner's connection in `MIGRATIONS_DATABASE_URL`. Migrations use `MIGRATIONS_DATABASE_URL` when it's set, and `DATABASE_URL` otherwise. `DATABASE_URL_POOLED` is for the API later. A connection string with `sslmode=require` (what Neon gives you) checks the server's certificate and hostname, like `verify-full`. For local Postgres without TLS, use `sslmode=disable` or leave `sslmode` out.

CI runs the same checks on every push and pull request.

### Docker

```sh
docker compose --profile jobs build                 # build the engine image
docker compose --profile jobs run --rm migrate      # create or update the tables
docker compose --profile jobs run --rm jobs         # crawl, ingest, identify, graph, scenes, export-map
docker compose --profile jobs run --rm jobs related "Ora Vance"
```

Settings come from `.env`, which stays out of the image. Fetched pages are kept in the `pages` volume.

### Explorer on localhost

```sh
docker compose --profile jobs run --rm jobs export-map   # write the map file into the map volume
docker compose --profile web up --build                  # serve the explorer on http://localhost:8080
```

The `web` service is Caddy with the built explorer ([0027](docs/decisions/0027-web-server.md)). It serves the map from the `map` volume and nothing else.

## Data & ethics

SoundShark only uses data sources whose terms allow it, respects rate limits and robots.txt, and stores audio *features*, never audio.

## License

MIT. See [LICENSE](LICENSE).
