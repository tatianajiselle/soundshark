# 0001. Open engine, private site adapters

**Status:** Accepted

## Context

Most of what is interesting in SoundShark is generic: a concurrent crawler, rate limiting, retries, a store of fetched pages, artist matching and graph scoring. None of that depends on any particular website.

The code that knows one website's HTML is different. It is small, it breaks whenever the site changes its layout, and publishing it would hand anyone a ready-made scraper for that site, whatever its owners think about that.

## Decision

The engine is open source under the MIT license, in the public `soundshark` repository. Site-specific adapters live in a separate private package and are loaded at runtime from configuration (`SOUNDSHARK_SOURCES=module.path:ClassName`). The public repository ships only the interface and a demo source with fictional artists, venues and events, so anyone can run it end to end without real data.

## Consequences

- All the reusable work is public and reviewable.
- The engine can't reach for site-specific shortcuts, because it never imports a real adapter. That keeps the interface honest.
- Deploys are built from the private side, which installs the public engine as a dependency.
- Anyone who wants real data writes their own adapter, for a site whose terms allow it.

## Alternatives considered

- **Everything public.** Simplest, but publishes scrapers for specific sites.
- **Everything private.** Hides the part worth sharing and learning from.
