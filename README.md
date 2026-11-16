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

The engine (`soundshark/crawler.py`) does all the fetching: a concurrent breadth-first crawl that never fetches a URL twice, paces requests per host, always obeys robots.txt (including `Crawl-delay`), retries timeouts, 429s and 5xx with backoff and `Retry-After`, skips pages that still fail, and returns on its own when there's nothing left to fetch.

A data source is a small plugin (`soundshark/sources/base.py`): its `seeds`, its `politeness` settings, `parse(page)` that turns a fetched page into events and links to follow, and `refresh_after(url)` that says when a stored copy is too old.

This repo ships only the interface and a **demo source with fictional data**. Site-specific adapters aren't published: they're loaded at runtime from your own package via `SOUNDSHARK_SOURCES`, a comma-separated list of `module.path:ClassName` (copy `.env.example` to `.env`; it defaults to the demo source).

```sh
uv run python -m soundshark        # runs the demo source by default
```

## Development

Uses [uv](https://docs.astral.sh/uv/). It installs the right Python and every dependency from the lockfile.

```sh
uv sync                 # create .venv and install everything
uv run pytest           # tests
uv run ruff check .     # lint
uv run ruff format .    # format
uv run pyright          # type check (also catches un-awaited coroutines)
```

CI runs the same checks on every push and pull request.

## Data & ethics

SoundShark only uses data sources whose terms allow it, respects rate limits and robots.txt, and stores audio *features*, never audio.

## License

MIT. See [LICENSE](LICENSE).
