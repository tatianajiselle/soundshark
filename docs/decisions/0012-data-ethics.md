# 0012. Data ethics: show connections, never copies

**Status:** Accepted

## Context

SoundShark is built on lineups that venues, promoters and listings put together and publish. That work deserves respect. The value SoundShark adds is the connections between artists, not a second copy of anyone's listings.

## Decision

- **Only use sources whose terms allow it**, and always obey robots.txt and the rate limits in [0003](0003-polite-crawling.md).
- **Show derived connections and scores, not copies.** The explorer doesn't republish lineup tables or mirror archives.
- **Credit and link back.** Every connection links to the original event pages, and sources are credited by name.
- **No bulk export.** There is no download of the dataset and no raw-data API.
- **Remove a source on request**, quickly and without argument.
- **Raw data is never published.** Fetched pages and crawl output stay private: they are ignored by git, a local pre-commit hook refuses data files, and CI fails if one is ever tracked.
- **Audio, in v2, is analysed and discarded.** Only derived features are stored, never the audio itself.

## Consequences

- Some useful views (full lineups, downloadable data) are deliberately not offered.
- Adding a source starts with reading its terms, not its HTML.

## Alternatives considered

- **Publishing the collected dataset.** Useful to others, but it isn't ours to publish.
