# 0017. Stop when a site pushes back

**Status:** Accepted

## Context

[0003](0003-polite-crawling.md) paces requests and retries temporary errors. That handles one slow or flaky page. It doesn't handle a site that is saying "stop" for everything: a crawler that backs off on each page but keeps working through a list of hundreds is still hammering a site that has asked it not to.

Redirects had a smaller gap: the HTTP library followed them immediately, so a redirected request skipped the pause between requests.

## Decision

- **A blocking answer stops the whole crawl.** Any 401, 403 or 451 ends the crawl: nothing else is fetched, and the reason is saved on the crawl run.
- **Trouble in a row stops the whole crawl.** After 5 pages in a row get no response, a 429 or a 5xx (each after its own retries), the crawl ends the same way. A missing page (404) is not trouble: the site answered, so it resets the count like any other answer.
- **Every redirect hop waits its turn**, like any other request to that site, up to 5 hops.
- A stopped crawl still saves what it fetched and its crawl run, with `error` saying why.

Both limits and the list of blocking statuses are part of each source's crawl policy.

## Consequences

- When a site pushes back, a person has to look before anything runs again.
- A burst of genuine outages can end a crawl early; re-running it later is cheap, because pages already fetched come from the store.

## Alternatives considered

- **Keep going and let retries back off.** Polite per request, impolite overall.
- **Switch IP addresses or slow down further and continue.** Working around a block is not something SoundShark does.
