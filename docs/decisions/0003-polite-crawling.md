# 0003. Crawl politely by default

**Status:** Accepted

## Context

Most of the sites with lineup history are small venues and community listings, not big platforms. A careless crawler is a real cost to them. Speed isn't a goal: the whole history of one venue is a few hundred pages, and waiting a few minutes for it is fine.

## Decision

The engine's defaults are deliberately slow and careful, and a source can only make them stricter unless there is a clear reason:

- **robots.txt is always obeyed**, including `Crawl-delay`.
- **One request at a time per site**, with **at least 2 seconds** between requests.
- **Backing off**: 429 and 5xx responses are retried a few times with growing waits, and `Retry-After` is respected.
- **An honest User-Agent** that names the project and points to its website.
- **Limits on every run**: a maximum depth and a maximum number of pages.
- **Failures don't stop the crawl.** A page that keeps failing is recorded and skipped.
- **Pages that can't change aren't fetched again** (see [0005](0005-idempotent-incremental-crawls.md)).

## Consequences

- A full crawl of one site takes minutes instead of seconds. That's acceptable.
- Different sites can be crawled at the same time, because the limits are per site rather than global.
- Tests check these rules directly against a fake website, so they can't quietly regress.

## Alternatives considered

- **Global concurrency only.** One slow site would block the rest, and one fast loop could hammer a single host.
- **Per-source politeness code.** Easy to forget; replaced by [0002](0002-engine-fetches-sources-parse.md).
