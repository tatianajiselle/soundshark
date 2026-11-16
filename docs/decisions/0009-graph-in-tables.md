# 0009. The graph is tables, computed nightly

**Status:** Accepted, amended by [0018](0018-relatedness-scoring.md) (top 50, scored with scipy)

## Context

The question "who is related to this DJ?" needs more than counting shared nights. A headliner who plays everywhere would otherwise look related to everyone. Good answers weigh b2b sets above sharing a room, a room above sharing a night, recent nights above old ones, and correct for how often each artist plays at all. That kind of scoring (for example personalized PageRank) is too heavy to run on every request.

## Decision

- The graph is ordinary rows: `artist_edges` holds one row per pair of artists who shared a bill, with counts for shared events, shared rooms, b2b sets, and when they first and last played together.
- A **nightly job** rebuilds the edges from the identity layer, runs the graph math in Python (networkx first, a faster library if needed), and stores the **top 20 related artists** for every artist.
- The API only reads precomputed answers. Path questions ("how are these two connected?") run a breadth-first search over the edge list.

## Consequences

- Lookups are instant, and the API stays simple.
- Answers are up to a day old. For lineup history, that doesn't matter.
- Scoring can be changed and re-run freely, since it is derived data.

## Alternatives considered

- **Compute on request.** Always fresh, but slow and expensive for the useful scores.
- **A graph database.** See [0006](0006-one-postgres-database.md): more to run, and no faster for graphs this size.
