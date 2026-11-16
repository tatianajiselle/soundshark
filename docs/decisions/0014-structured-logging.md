# 0014. Structured logging: named events with context

**Status:** Accepted

## Context

A crawl runs unattended on a server. When something goes wrong (a site starts returning 503s, robots.txt changes, a parser breaks on a new layout) the logs are the only record. Free-text log lines are hard to search and hard to connect: which crawl did this retry belong to?

## Decision

Log with [structlog](https://www.structlog.org/): every line is a **named event** with **key–value fields**, and every line of a crawl carries its `source` and `run_id`.

| Event | When |
|---|---|
| `crawl.started` / `crawl.finished` | once per crawl; `finished` has every count and the duration |
| `robots.loaded` / `robots.missing` / `robots.unreachable` | once per site, with what it means for the crawl |
| `page.blocked_by_robots` | a URL robots.txt doesn't allow |
| `http.retrying` / `http.gave_up` | each retry with its reason and wait, and the final give-up |
| `http.unexpected_status` | a page that answered 404, 403, ... |
| `page.parse_failed` | a parser exception, with the traceback |
| `http.response`, `page.parsed`, `page.from_store` | per request and page, only with `-v` |

On a laptop the output is readable coloured lines; on the server, `--log-json` prints one JSON object per line. Run ids start with the UTC time (`20261116T025213Z-4ad3df`) so they sort and say when the run began.

## Consequences

- "Every retry for this run" or "every parse failure this week" is a filter, not a regex.
- Tests check that events fire with the right fields, so the logs can't silently rot.
- One more dependency.

## Alternatives considered

- **The standard `logging` module with formatted strings.** No dependency, but context has to be repeated by hand in every message.
- **Metrics instead of logs.** Worth adding later (pages per minute, error rates); they don't replace a record of what happened to a specific URL.
