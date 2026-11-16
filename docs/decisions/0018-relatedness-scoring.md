# 0018. Relatedness: weighted nights, personalized PageRank, top 50

**Status:** Accepted. Amends [0009](0009-graph-in-tables.md): 50 related artists instead of 20, and the scoring runs on scipy, checked against networkx.

## Context

[0009](0009-graph-in-tables.md) settled that the graph is tables and that a nightly job precomputes the answers. This records how a pair of artists is weighed and how "related" is scored.

## Decision

**Edges.** One row per pair of artists who shared a bill, counted once per night:

| On the same night they were… | Weight |
|---|---|
| b2b (the same lineup slot) | 4 |
| in the same room | 3 |
| in different rooms | 0.25 |

- **The room matters most.** At a club with several rooms, the room is the best available stand-in for sound: one room might be mostly techno, another mostly house. A different-room night still counts a little, so a venue's rooms stay loosely connected for paths and scenes. With the first weights tried (3 / 2 / 1), an artist who often played the other room on the same nights could rank near the top of someone's list without ever sharing their room; with these weights, such artists drop out of the top 50.
- Each night's weight **halves every 3 years** of age; upcoming nights count fully.
- Each pair's total is divided by √((nights of A + 5) × (nights of B + 5)), so artists who play constantly don't end up related to everyone. The **+5** keeps artists with only one or two nights from looking closer than regulars: without it, a single shared night with a one-off guest outweighs years of nights with a regular.

**Scores.** For every artist, **personalized PageRank** on that weighted graph (damping 0.85): a random walk along shared bills that keeps jumping back to the artist. Artists the walk visits most are the most related, which includes artists who never shared a bill but share many of the same people.

- The **top 50** per artist are stored in `related_artists`. `artist_edges` keeps every pair, so nothing about the graph itself is cut.
- All artists are scored together in batches with sparse matrices (scipy), which takes seconds instead of calling networkx once per artist. A test checks the scores against `networkx.pagerank` on random graphs.
- The job replaces both tables in one transaction, with Postgres `COPY`, so readers never see a half-built graph.
- `related` reads only stored rows, and shows the evidence for each answer: nights together, same room, b2b, and the last time.

## Consequences

- Recent collaborators rank above long-ago ones; a three-year half-life makes a 2016 night worth about a tenth of a 2025 one.
- All weights live in one settings object (`GraphScoring`), so they can be tuned and the job re-run in under a minute.
- Scores are relative within one artist's list; they are not comparable across artists.

## Alternatives considered

- **Count shared nights.** Simple and explainable, but misses two-hop closeness and lets the busiest artists dominate.
- **Ignore different-room nights entirely (weight 0).** Nearly the same rankings, but splits each venue's rooms into separate graphs.
- **networkx `pagerank` per artist.** The reference implementation, but rebuilds the matrix on every call: minutes instead of seconds for every re-run.
- **Store every score.** About 44 million rows for the current archive, almost all of them noise.
