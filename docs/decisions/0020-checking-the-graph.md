# 0020. Checking the graph: a backtest, a comparison of settings, and a list of movers

**Status:** Accepted.

## Context

[0018](0018-relatedness-scoring.md) chose the weights by looking at a handful of lists and asking whether they felt right. That doesn't scale and can't tell a real improvement from a change that only moves a few familiar names. Every weight lives in `GraphScoring`, so trying a new setting is cheap; what was missing is a way to say whether it made the rankings better or worse, and whose lists it changed.

There is no ground truth for "sounds alike" yet ([v2](../README.md) will listen to the music). The best stand-in in the lineup data is the same one the edges already lean on: artists booked into the same room on the same night usually share a sound.

## Decision

**A backtest.** `soundshark evaluate` splits every credit at a cutoff date (default 2025-06-01). The graph is built only from the nights before it, as if it were that day, and the rankings are checked against the nights after it. The targets are later **same-room partners**: pairs of artists who share a room on a night after the cutoff, both of whom already played before it (nobody can rank an artist the graph has never seen).

| Metric | What it asks |
|---|---|
| recall@10 | Of each artist's later same-room partners, how many are in their top 10? Summed over artists and divided by the most that could fit (at most 10 each). |
| new partners recall@50 | The same, but only for later partners they had never shared a room with before the cutoff, against the top 50. This is the part a count of past nights can't do: predicting a meeting that hasn't happened yet. |
| home room share@10 | For artists with 5+ nights before the cutoff and a full top 10, the share of that top 10 whose most-played room (per venue) is the artist's own. A check that the room profiles keep lists inside one sound. |

**Rows to compare, not a score to chase.** Each run prints the same metrics for:

- **count shared nights**: direct neighbours ranked by nights together, no weights and no PageRank. The floor any scoring has to beat.
- **defaults**: the current `GraphScoring()`.
- **each variant**: `--variant name:field=value[,field=value]` overrides any `GraphScoring` field; unknown fields and values of the wrong type are refused. Without `--variant`, three built-in variants run: room profiles off (floor 1), room profiles at full strength (floor 0), and a 5-year half-life.

The numbers depend on how much data there is, how busy the rooms are and where the cutoff falls, so they only mean something next to each other in one run. A setting is worth adopting when it beats the defaults on the metric it was meant to move without losing much on the others. `--json` prints the same result as one object, for scripts.

**Movers.** `soundshark movers --set field=value [--set ...]` builds the graph on every credit twice, once with the defaults and once with the overrides, and compares each artist's top N (default 10) for artists with 5+ nights. Change is 1 − |A∩B| / |A∪B| of the two top-N sets. The biggest movers come first (then busier artists, then by name), with who entered and who left. A backtest says whether a change helps on average; movers say where to look before trusting it.

**A taste check, kept private.** The last check is a person's own knowledge: pairs of artists they know should be close, and pairs they know shouldn't. Those lists name real artists and depend on private data, so they live outside this repo, next to the private source adapters ([0001](0001-open-engine-private-adapters.md)). Nothing from them, and no numbers from the private archive, goes into public code, docs or commits.

The metric code (`services/graph_evaluation.py`, `services/ranking_changes.py`, `services/scoring_variants.py`) takes plain lists of credits and returns dataclasses; only the commands touch the database. PageRank runs in a worker thread, as in the nightly job.

## Consequences

- A change to the weights comes with evidence: a before-and-after table and a list of whose rankings moved.
- Same-room nights are both what the graph is built from and what it is graded on, so the backtest rewards predicting bookings, not sound. A setting that wins only because it predicts bookings better can still make lists worse to a listener; that's what the movers and the taste check are for.
- Only artists who played before the cutoff count, so a cutoff too close to the end of the data leaves few targets, and one too far back trains on little.
- Each command rebuilds the graph once per row, so a run takes a few PageRank passes; it doesn't write anything.

## Alternatives considered

- **Hand-picked lists only.** What 0018 did. Good at spotting nonsense, bad at telling two reasonable settings apart, and it only ever looks at familiar artists.
- **Hold out random nights instead of a date.** Leaks the future into training: a residency's later nights would help predict its earlier ones.
- **Any shared night as the target.** Rewards ranking everyone on a big bill, which is exactly what the room weights try to avoid.
- **A single combined score.** Easier to sort by, but it hides which trade a setting makes.
- **Diff the stored `related_artists` table for movers.** It may be stale or built with other settings; computing both lists in one run compares exactly the two settings asked about.
