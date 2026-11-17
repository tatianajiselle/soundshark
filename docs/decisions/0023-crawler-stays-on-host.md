# 0023. The crawler stays on the host it was sent to

**Status:** Accepted. Tightens [0017](0017-stop-when-a-site-pushes-back.md) on redirects.

## Context

The crawler runs on a cloud server. Before this, it followed any redirect to any address, up to 5 hops. A site, or anyone who controls one of its pages, could send it to another host, to a private or loopback address, or to the cloud metadata address. It also read every response into memory whole, so one huge or endless answer could use up memory or disk.

## Decision

- **Redirects stay on the requested host.** A redirect is followed only if it is `http` or `https` and has the same host name as the URL first requested, ignoring case. Every hop is checked against that first URL.
- **Two small changes are allowed on that host:** `http` to `https`, and a move to the default port of the scheme. Going from `https` to `http`, or to another port, is refused.
- **A refused redirect is not fetched.** The redirect answer itself comes back, like a redirect past the 5-hop limit, so the page is recorded as failed with its 3xx status. The log says `http.redirect_refused` with the URL and the target.
- **Responses have a size limit,** 10 MiB by default (`max_response_bytes` in the crawl policy). A `Content-Length` over the limit is refused before the body is read. Otherwise the body is streamed and reading stops as soon as it passes the limit. The limit counts the decoded bytes, so a small compressed body can't grow past it.
- **An oversized response is a failed page,** with the status it answered and the reason `response larger than N bytes`, logged as `http.response_too_large`. It is not retried: the same page would be just as big.
- **robots.txt goes through the same client**, so the same rules apply. A robots.txt that redirects off the host, or is too large, is treated like an unreachable one: nothing on that site is crawled.

## Consequences

- A site that moves to another host name, such as from the bare name to `www`, must be crawled from its new name. Its source's seed URLs have to say so.
- A page that only fails because of these rules shows a 3xx status or the size reason on the crawl run, so it is easy to spot.
- A very big page, such as a long archive on one page, fails instead of being stored. Its source's crawl policy can raise the limit.

## Alternatives considered

- **Allow any public address and block private ones.** Needs DNS lookups at the right moment and still lets a site send the crawler to strangers.
- **A list of allowed hosts per source.** More flexible, but no source needs it yet. It can be added to the crawl policy later.
- **Parse only the first part of a large page or robots.txt.** A cut-off page parses into wrong or missing events, and a cut-off robots.txt could drop rules.
