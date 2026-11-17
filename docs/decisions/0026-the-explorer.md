# 0026. The explorer is a static map: one file, drawn in the browser

**Status:** Accepted. Changes how [0010](0010-read-only-explorer.md) is served: no API in v1.

## Context

[0010](0010-read-only-explorer.md) planned a small FastAPI app behind the explorer. The questions people ask first are about the whole graph: what the scenes are, who sits near whom, and how two DJs are connected. Those need every artist and every top-10 list at once, which a page-at-a-time API is bad at and a single file is good at. The graph is rebuilt nightly anyway, so the data only changes once a day.

## Decision

- **A static app in `explorer/`**: Vite, React and TypeScript, built into plain files. In production Caddy serves the app at `/` and the engine's `map.json` at `/map.json`, on the same origin. There is no API and no database connection from the browser.
- **One file holds the map.** `map.json` has a version, when it was made, credits, scenes, artists (id, name, aliases, nights, scene) and each artist's top 10 related as `[source, target, score]`. The app checks the version and the shape when it loads and shows a plain error when the file is missing or wrong. Credits come only from the file, so no source is named in the app.
- **Three views.**
  - The **whole map**: every artist is a point sized by nights, every related pair is a line, and the colour is the scene. The twelve biggest scenes get their own colour and the rest are grey. A legend lists the scenes, and clicking one picks out its members.
  - **Focus**: one artist in the middle, with everyone one, two and three hops away (over related pairs, either direction) brightened by hop and everything else dimmed. A panel shows the artist and their top related list from the file.
  - **Path**: the shortest chain between two artists (fewest hops), drawn on the map and listed as A → X → Y → B, or "no path within the map".
- **The address keeps the view**: `#a=<id>` for focus and `&b=<id>` for a path, so a view can be shared and reloaded.
- **Search** matches names and aliases, ignoring case, accents and punctuation. Names that start with the query come before names that only contain it, then busier artists first.
- **Graph logic is plain TypeScript** (checking the file, the adjacency lists, hops, shortest paths, search and colours), with unit tests. React only draws.
- **Cosmograph draws the graph.** It lays out and renders tens of thousands of points on the GPU. Its licence is CC BY-NC 4.0, which allows non-commercial use with credit; the explorer is non-commercial ([0010](0010-read-only-explorer.md)), credits it in the about text, and keeps its logo on the map. Cosmograph 2 keeps its data in DuckDB-WASM, which the app ships itself instead of loading it from a CDN, and its usage reporting is replaced with a stub, so the page makes no requests to other hosts.
- **Developed against a fake map.** `npm run fake-map` writes an invented map (made-up names, planted scenes, a few accented aliases, a small island with no path to the rest). No real `map.json` is ever committed.

## Consequences

- Hosting is a folder of files, and the explorer can't fall over under load or reach the database.
- The browser downloads the whole map: a few MB of JSON for the current graph, plus about 8 MB (compressed) of DuckDB the first time. That is fine on a desktop and slow on a weak phone connection.
- Everyone can read `map.json`. It holds only derived data (names, counts, scene labels and scores), never lineups, dates or venues, in line with [0012](0012-data-ethics.md), but it is a download of the derived graph.
- Linking each connection back to the original event pages ([0012](0012-data-ethics.md)) needs more than the file has. It is not in v1.
- Cosmograph's licence rules out commercial use of the explorer while it draws the map.
- The page needs `'wasm-unsafe-eval'` for DuckDB and `'unsafe-inline'` styles for Cosmograph in its Content-Security-Policy, and nothing from other origins.

## Alternatives considered

- **The FastAPI app from 0010.** Needed for per-artist pages later, but every view here wants the whole graph, and an API adds a server, a database role and a load problem.
- **Server-rendered images of the graph.** Cheap to serve, but not explorable.
- **cosmos.gl (MIT) instead of Cosmograph.** The open GPU engine underneath, with no DuckDB and no licence limit, but it leaves labels, data handling and much of the interaction to us. Worth revisiting if the licence or the download size becomes a problem.
- **Sigma.js or D3.** Fine for a few thousand nodes; the map has to stay smooth at tens of thousands.
