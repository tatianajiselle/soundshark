# 0025. The map file: one static JSON of derived data

**Status:** Accepted. Follows [0010](0010-read-only-explorer.md) and [0012](0012-data-ethics.md).

## Context

The explorer's first view is a map of every artist, coloured by scene ([0024](0024-scenes.md)), with lines to each artist's closest neighbours. The browser needs the whole graph at once to lay it out, and the answer changes once a night. Serving it from the API on every request would rebuild the same answer thousands of times. A static file built by the nightly job does it once.

That file is published on a website, so anyone can download it. [0012](0012-data-ethics.md) says SoundShark shows derived connections and never republishes the lineups it learned them from. The file has to hold to that by construction, not by care.

## Decision

**`soundshark export-map`** writes the file the explorer loads, by default `data/map/map.json`, and `soundshark jobs` runs it after `scenes`. The format is a contract with the explorer:

```json
{
  "version": 1,
  "generated_at": "2026-11-17T04:31:00+00:00",
  "credits": [{"name": "Some Source", "url": "https://example.org/"}],
  "scenes": [{"id": 3, "label": "A / B / C", "size": 412}],
  "artists": [{"id": 17, "name": "Display Name", "aliases": ["Other Spelling"], "nights": 53, "scene": 3}],
  "related": [[17, 42, 0.012345]]
}
```

- **`artists`**: every artist with related artists, by id. `aliases` are other display spellings of the name, so search finds them; spellings that differ only in case are dropped, and there are at most 10. The internal matching keys stay out. `nights` is how many nights they played in total, and `scene` is their scene's id or `null`.
- **`related`**: each artist's top 10 as `[artist, other, score]`, ordered by artist then rank. Scores keep 6 significant digits, plenty to rank and draw by. 10, not the stored 50: it's what the map draws, and it keeps the file small.
- **`scenes`**: every scene, largest first.
- **`credits`**: one entry per configured source, with its name and the origin of its first seed URL, so the explorer can credit and link back ([0012](0012-data-ethics.md)).
- **`version`** changes only when a change would break a reader. Adding a field doesn't, but it still changes the contract (below).

**Derived data only.** The file never contains dates of nights, rooms, venues, events, lineups, b2b flags or per-pair night counts. Those are the archive itself; together they would let anyone rebuild the lineups. Names, total nights, scores and scenes say who is close to whom without saying where or when. A test walks the produced JSON and checks the exact keys at every level, so adding a field fails it until someone decides to change the contract.

**Written so a reader never sees half a file.** The command writes `map.json` and `map.json.gz` (the same bytes, gzipped) to temporary files in the same directory, then moves each into place with an atomic rename. A web server reading while the job writes gets the old file or the new one. The JSON is compact (no spaces) UTF-8 with names as written, not `\u` escapes. The gzip carries no timestamp, so the same data gives the same bytes. The files are readable by everyone (mode 644), since they're meant to be served.

**Gzip next to it, made once.** Names and ids compress well. Web servers can send a pre-compressed copy to browsers that accept it (`gzip_static`, `precompressed`), so compressing once at export saves the server doing it on every request. The plain file stays for servers and tools that don't.

**In the image**, `/app/data/map` exists and belongs to the `soundshark` user, so a volume mounted there starts out writable by the jobs.

The payload is built from plain rows (`services/map_export.py`) and tested without a database; a database test exports from a real build and checks the contract.

Scene labels can be replaced by hand-written names from a TOML file (`SOUNDSHARK_SCENE_NAMES`, a `[names]` table of scene id = name). The names are an editor's reading of the data, so they live with the deployment, not in this repo. Scene ids are kept across runs ([0024](0024-scenes.md)), so a name stays on its scene until that scene splits, merges or disappears.

## Consequences

- The explorer's map is one static download, cacheable, with no API call.
- The map is up to a day old, like everything else ([0009](0009-graph-in-tables.md)).
- Anything new the map should show has to be argued into the contract first, and checked against [0012](0012-data-ethics.md).
- A large archive makes a large file. Gzip and the top-10 cut keep it manageable; splitting it into tiles would be a new decision.

## Alternatives considered

- **An API endpoint that builds the map on request.** Always fresh, but the same work on every visit, for data that changes once a night.
- **Include the evidence (nights together, last time together).** The explorer shows that per pair from the API ([0010](0010-read-only-explorer.md)), next to a link to the original page, rather than in a bulk file anyone can download.
- **Pretty-printed JSON.** Easier to read, noticeably bigger; `python -m json.tool` reads the compact file just as well.
- **Brotli.** Smaller still, but one more dependency; gzip is in the standard library and every server and browser speaks it.
- **Write in place.** Simpler, but a reader could catch a half-written file.
