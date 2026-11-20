---
name: review-graph
description: Review how well SoundShark's related-artist rankings hold up, all artists at once. Use when the user asks to review, check or verify the graph, after `soundshark graph` rebuilds, before or after any change to GraphScoring weights, identity rules or ingest, or when they question a specific ranking ("X shouldn't be near Y").
---

# Review the graph

Judge the rankings with three checks instead of reading lists one by one ([decision 0020](../../../docs/decisions/0020-checking-the-graph.md)):
- `evaluate`: a backtest. Build the graph from nights before a cutoff, then score it against who actually shared a room afterwards.
- A taste check: pairs the user knows should or shouldn't be close.
- `movers`: the artists whose top 10 a change would move most. These are the only lists worth reading by hand.

Run the commands where the deployment runs, with `DATABASE_URL` set. Never print it.

## Steps

1. **Is the graph fresh?** Run `uv run soundshark related "Ora Vance" --limit 1`, using any artist in the archive.
   - The header shows when the graph was computed.
   - If the scoring code, identity rules or data changed since then, run `uv run soundshark identify` (add `--rebuild` if identity rules changed), then `uv run soundshark graph`.
2. **Backtest:** `uv run soundshark evaluate --json > reviews/$(date +%F)-evaluate.json`.
   - With no `--variant`, it compares the defaults against `floor-1`, `floor-0` and `half-life-5`.
   - For a proposed change, add `--variant "name:field=value,field=value"`. The fields are those of `GraphScoring`.
3. **Taste check:** run the user's own list of known pairs (see below). Report each pair that fails, with its actual rank.
4. **Movers**, when a change is on the table: `uv run soundshark movers --set field=value --limit 15`.
   - For the top 3 movers, show what entered and what left their top 10.
   - Use `uv run soundshark related NAME` when the evidence (nights together, same room) helps.
5. **Compare with the last review.** Diff against the newest earlier file in `reviews/`.
   - Flag a drop of more than 0.01 in any metric on the `defaults` row.
   - Flag any taste check that used to pass and now fails.
6. **Report in chat.** Give:
   - the metrics table, with changes against the last review;
   - taste-check failures, with each pair's actual rank;
   - the movers worth reviewing by hand;
   - a recommendation.
   Lead with the verdict: the change helps, hurts, or makes no difference.

## The taste check

The list names real artists, so it lives with the deployment, never in this repo. One way to write it is a TOML file:

```toml
[[close]]
artist = "Ora Vance"
other = "Mirek Sol"
within = 5
note = "same crew, same sound"

[[apart]]
artist = "Ora Vance"
other = "Tamsin Rook"
beyond = 10
note = "shared a bill once; different genres"
```

A `close` pair passes when `other` is within the artist's top `within`. An `apart` pair passes when `other` is not in the artist's top `beyond`.

## Reading the numbers

- **recall@10:** later same-room partners found in the top 10.
- **new partners@50:** later partners who had never shared a room before, found in the top 50. This is the discovery the graph exists for.
- **home room@10:** share of the top 10 who usually play the artist's room. It stands in for "same sound" at venues with several rooms.
- **Compare rows with each other; never read a number as a grade.** The backtest mostly reflects a few venues' booking choices.
- A change that raises recall@10 but lowers the other two has made the lists more like who gets booked together, not more like who sounds alike. Prefer the last two metrics.
- If a pair fails the taste check, believe the user's knowledge over the metrics, and look for why the graph disagrees.

## When the user questions a ranking

When the user says something like "X shouldn't be that close to Y" or "X is really a house DJ":
1. Find out why. Look at the evidence: shared nights, rooms, how many nights each artist has, and whether a "presents" or hosted night is involved.
2. Add the pair to the taste check: `apart` with `beyond = 10`, or `close` with `within = N`, plus a `note`. Then the next review catches it automatically.
3. Change the scoring only if the backtest and the movers say the fix generalises.

## Privacy

- Real artist names, venue and room names, and every number from a real archive are private data ([decision 0012](../../../docs/decisions/0012-data-ethics.md)).
- Keep them in chat and in the deployment's own files.
- Never put them in this repo, its docs, commits, PR titles or bodies, or comments. Describe scoring changes here in generic terms, and use the demo artists in examples.
