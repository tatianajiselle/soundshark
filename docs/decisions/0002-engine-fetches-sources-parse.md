# 0002. The engine fetches; sources only parse

**Status:** Accepted

## Context

The first version of the source interface let each source fetch its own pages: `events(client)` was an async generator that did whatever HTTP it liked and yielded events.

That makes each source a small crawler of its own. Every source would reimplement queueing, concurrency limits, pacing, retries and robots.txt checks, and the engine couldn't guarantee any of them. It also couldn't save pages before parsing them (see [0004](0004-fetch-once-parse-many.md)), because it never saw the pages.

## Decision

The engine does all the fetching. A source describes a site instead of crawling it:

- **seed URLs** to start from
- **`parse(page)`**, which turns one fetched `Page` into a `ParsedPage`: the events found on it and the links worth following
- a **crawl policy** for that site (how many requests at once, how far apart, how many retries), and how long a fetched page stays fresh

The engine owns the breadth-first crawl, the queue, workers, rate limits, robots.txt, retries, the raw store and crawl-run records.

## Consequences

- Politeness is enforced in one place, for every source.
- A source becomes a pure function from page to data, which is easy to test with saved or hand-written pages and no network.
- Re-parsing stored pages after a parser fix uses the very same `parse` method.
- Sources that aren't link-following websites (a JSON API, a CSV feed) still fit: their "links" are the next pages or files.

## Alternatives considered

- **Keep `events(client)`, with the engine as a helper library sources may call.** Less change, but nothing stops a source from skipping the helper.
- **A full framework such as Scrapy.** Mature, but hides exactly the async machinery this project exists to learn.
