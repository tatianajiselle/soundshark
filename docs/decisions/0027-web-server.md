# 0027. Caddy serves the explorer and the map file

**Status:** Accepted. Fills in [0011](0011-one-small-server.md) for the explorer ([0026](0026-the-explorer.md)).

## Context

The explorer is a static app, and the map file ([0025](0025-the-map-file.md)) is rewritten by the nightly jobs. Nothing public needs to run Python or reach the database, so the web side can be a plain file server. It should be the only thing on the server that listens, and it should be hard to turn into anything else.

## Decision

- **A web image** (`web/Dockerfile`): Node builds the explorer, then the built files and `web/Caddyfile` go into a Caddy image. It runs as uid 1000 with a read-only filesystem, no Linux capabilities and `no-new-privileges`. Caddy's file capability for binding low ports is removed, so it listens on 8080 and 8443 and the host maps 80 and 443 to them.
- **One shared volume, `map`:** the jobs write `map.json` and `map.json.gz` to it, and Caddy mounts it read-only. The page store is a different volume and is never mounted into the web container.
- **Routes:** `/map.json` is served from the map volume, using the gzip copy when the browser accepts it, with `Cache-Control: no-cache` so a new night's map shows up. `/assets/*` has hashed names and is cached for a year. Everything else comes from the built app with `no-cache`.
- **Headers:** a strict Content Security Policy (only the site's own scripts, styles, workers and requests), `nosniff`, no referrer, no framing, and no `Server` header. The admin API is off.
- **The address comes from `SITE_ADDRESS`.** Unset, Caddy serves plain HTTP on any host, which is the local setup; Compose binds it to `127.0.0.1` only. On the server it is the domain, and Caddy gets and renews the certificate itself.
- **Server-only settings go in `/etc/caddy/site.d/*.caddy`,** imported into the site block. The folder is empty locally; on a server it holds settings that don't belong in the repo.

## Consequences

- `docker compose --profile web up` serves the explorer on `http://localhost:8080` from whatever map the jobs last wrote.
- Locally, Caddy's data directory is a tmpfs. On the server it needs a real volume, or certificates are requested again on every restart.
- Changing the Caddyfile or the explorer means rebuilding the web image; a new map needs nothing but the nightly jobs.

## Alternatives considered

- **Caddy on the host instead of in Compose.** One less container, but the host would need its own package and config, and the local and server setups would differ.
- **nginx.** Just as capable for static files, but certificates would need a second tool.
- **Mounting the page store into the web container** and pointing the root at a subfolder. One volume fewer, but the raw pages would then sit one configuration mistake away from being public.
