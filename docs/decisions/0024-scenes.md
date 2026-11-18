# 0024. Scenes: a consensus of community detection runs over each artist's top 10

**Status:** Accepted. Builds on [0018](0018-relatedness-scoring.md).

## Context

The roadmap promised automatic scene detection: groups of artists who belong together, so the explorer can colour a map by scene and say "this artist is part of that crowd". [0018](0018-relatedness-scoring.md) already gives every artist a ranked list of the 50 artists closest to them. Scenes should come from that same graph, every night, without anyone naming them by hand.

Three things make this harder than running a clustering function once:

- Related scores are relative within one artist's list ([0018](0018-relatedness-scoring.md)); a busy artist's scores are not comparable with a quiet one's.
- Community detection is randomized. With a fixed seed it repeats exactly, but the slightest change to the input (one more night, a little more decay) can move scene boundaries, and the algorithm numbers its communities from scratch each time.
- A scene needs a name people recognise.

## Decision

**The graph.** Each artist's top 10 related artists, as an undirected weighted graph.

- Each artist's 10 scores are divided by their sum, so every artist casts the same total weight. Raw scores would let artists with concentrated lists outvote everyone else.
- The two directions of a pair are **added**. A pair that appears in both lists is stronger evidence than a pair that appears in one, and the sum counts it twice; the maximum would treat a mutual pair and a one-sided one the same. Adding also keeps the total weight equal to the number of artists, whatever the lists say.
- **10, not 50.** Fewer neighbours leave thin links and scenes that break apart on small changes; more let busy regulars bridge scenes, and the largest scenes swallow smaller ones. 10 is also how many the explorer shows.

**Communities.** Modularity, at resolution 1.5:

1. Louvain runs 10 times, with seeds 7 to 16.
2. A consensus graph keeps each edge whose two artists landed in the same community in at least half of the runs, weighted by its original weight times that share.
3. Leiden (seed 7) runs once on the consensus graph. Its communities are always connected, which Louvain doesn't guarantee.

A single run is deterministic but jumpy: on the real archive, rerunning after tiny changes moved a noticeable share of artists to other scenes. Most of those were artists the runs disagree about anyway, and the consensus settles them, so the same small changes move far fewer. It costs about ten times a single run, still a few seconds for thousands of artists.

**Resolution 1.5 instead of the standard 1.0.** At 1.0 the largest scenes were broad groupings, and at 1.5 each of them split into groups that read as distinct crowds. Pairs a listener knows belong together stayed together at both, pairs known to be apart stayed apart, and stability was the same. Higher still mostly multiplied small scenes.

**Small groups get no scene.** A community with fewer than 15 artists gets no scene, so colours go to real scenes. Most of these are small islands of the graph: a few artists from a handful of nights with nobody else in common.

**Stable ids.** Each new scene is matched to last night's scene it overlaps most:

- A pair is a candidate when the Jaccard overlap of their members is at least 0.3.
- Candidates are taken greedily, largest shared membership first; each old id is used at most once.
- A scene with no match gets a new id: the highest existing id plus one. Ids retired tonight are never given to a different scene in the same run.

When a scene splits, the larger part keeps the id and the other gets a new one. When two merge, the merged scene keeps the id it shares most members with, and the other id retires.

**The label** is the scene's three most-booked members, by nights, ties broken by name: "A / B / C".

**Tables and the job.** Migration 0003 adds `scenes` (id, label, size, computed_at) and `artist_scenes` (one row per placed artist; artists without a scene have no row). `soundshark scenes` reads `related_artists` and last night's scenes, clusters in a worker thread, and replaces both tables in one transaction. `soundshark jobs` runs it after `graph`. `--top`, `--resolution` and `--min-size` override the defaults for experiments; all settings live in `SceneSettings`. The clustering code (`services/scenes.py`) takes plain dictionaries and is tested on planted graphs without a database.

**The library: networkx 3.7, now a runtime dependency.** It was already used in tests ([0018](0018-relatedness-scoring.md)).

- It is pure Python, one wheel for every platform, so it installs on CPython 3.14 on macOS arm64 and on Linux x86_64 and aarch64, in the slim image, with nothing to compile.
- It has Louvain, modularity, and since 3.7 its own Leiden; earlier versions only passed Leiden on to other backends, hence the lower bound.
- Every run is deterministic with a seed, and the whole job takes seconds at this size.

## Consequences

- The same related artists always give the same scenes and the same ids.
- Scene ids carry over from night to night, so the map's colours mostly stay put. They are continuity, not permanent names: if the highest id retires, a later night can hand it to a new scene.
- Labels change when a scene's busiest artists change.
- Some artists have no scene. On the map they are uncoloured, not wrong.
- Scenes are derived data: changing a setting and re-running `soundshark scenes` rebuilds them from `related_artists`.

## Alternatives considered

- **igraph with leidenalg.** Faster, written in C, and the reference Leiden. But it adds two compiled packages whose wheels must exist for every Python and platform the laptop and image use, for speed this job doesn't need.
- **One Louvain or Leiden run.** Simpler and faster, but scene boundaries jump with tiny changes to the input.
- **The Constant Potts Model** (networkx's Leiden default). Its resolution is an absolute density, so the right value drifts as the archive grows; modularity's is relative to the graph's size.
- **Cluster `artist_edges` directly.** That is raw co-booking, which the room weights and PageRank were built to correct; the related lists already are the corrected view.
- **Label propagation, or k-means on an embedding.** The first is unstable on graphs like this; the second needs the number of scenes up front.
- **Optimal id matching (Hungarian on Jaccard).** Slightly better in rare ties, harder to explain, and greedy by shared members already gives splits and merges sensible ids.
- **Keep retired ids forever.** Would need a table of every scene ever seen, for little gain while the map only needs continuity from one night to the next.
