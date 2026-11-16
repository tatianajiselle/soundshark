# 0013. Code is grouped by role, and names say what things do

**Status:** Accepted

## Context

The first version kept everything in a few flat modules. The crawler module held the breadth-first crawl *and* the HTTP politeness (pacing, retries, robots.txt), so neither could be read or tested on its own. Names were short and needed context to understand: `Parsed`, `politeness`, `refresh_after`, `RawStore`, `normalize`.

The code is also meant to be read by people who didn't write it, often months later, without comments or docstrings to lean on.

## Decision

Group the code by the role it plays:

- **`models/`**: plain data, no I/O
- **`interfaces/`**: the contracts the engine depends on (`Source`, `PageStore`), written as `typing.Protocol` so implementations don't have to inherit anything
- **`clients/`**: everything that talks to websites (`PoliteHttpClient`, `RobotsRules`)
- **`services/`**: the logic (the crawler, artist identity)
- **`stores/`**: implementations of `PageStore`
- **`utils/`**: small, truly generic helpers only

And name things for what they do, in full words, with units where there are units: `seed_urls`, `links_to_follow`, `refetch_after`, `seconds_between_requests_per_host`, `pages_blocked_by_robots`, `matching_key`, `split_lineup_slot`. The code has no comments or docstrings; the names, the tests and these notes carry the meaning.

## Consequences

- The crawler reads as just the breadth-first crawl; the polite HTTP behaviour is tested directly in `clients/`.
- Longer names, a few more files.
- No `abstract/` folder: both contracts are Protocols. A base class with shared code would live in `interfaces/` if one is ever needed.

## Alternatives considered

- **Group by feature** (`crawl/`, `identity/`, `storage/`). Also reasonable; grouping by role makes the dependency direction obvious (services depend on interfaces and clients, never the reverse).
- **Docstrings for meaning.** They drift from the code silently; names and tests fail loudly when they're wrong.
