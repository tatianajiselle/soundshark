import { describe, expect, it } from "vitest";
import { buildGraph, componentSizes, edgesAlong, hopsFrom, mainIndices, relatedBySource, shortestPath } from "./graph";
import type { Artist, RelatedRow } from "./mapFile";

function artists(...ids: number[]): Artist[] {
  return ids.map((id) => ({ id, name: `Artist ${id}`, aliases: [], nights: id, cities: [], pos: null, scene: null }));
}

const chainArtists = artists(10, 20, 30, 40, 50, 60, 70);
const chainRelated: RelatedRow[] = [
  [10, 20, 0.5],
  [20, 10, 0.4],
  [20, 30, 0.3],
  [30, 40, 0.2],
  [40, 50, 0.1],
  [10, 30, 0.05],
  [60, 70, 0.9],
];

describe("buildGraph", () => {
  it("maps ids to positions", () => {
    const graph = buildGraph(chainArtists, chainRelated);
    expect(graph.size).toBe(7);
    expect(graph.indexById.get(30)).toBe(2);
    expect(Array.from(graph.ids)).toEqual([10, 20, 30, 40, 50, 60, 70]);
  });

  it("treats rows as undirected and keeps one edge per pair", () => {
    const graph = buildGraph(chainArtists, chainRelated);
    expect(graph.edgeCount).toBe(6);
    const pairs = Array.from(graph.edgeSource, (a, e) => [a, graph.edgeTarget[e]]);
    expect(pairs).toContainEqual([0, 1]);
    expect(pairs.filter(([a, b]) => a === 0 && b === 1)).toHaveLength(1);
    for (const [a, b] of pairs) expect(a).toBeLessThan(b);
  });

  it("builds adjacency both ways", () => {
    const graph = buildGraph(chainArtists, chainRelated);
    const neighboursOf = (i: number) =>
      Array.from(graph.neighbours.slice(graph.offsets[i], graph.offsets[i + 1])).sort();
    expect(neighboursOf(0)).toEqual([1, 2]);
    expect(neighboursOf(2)).toEqual([0, 1, 3]);
    expect(neighboursOf(4)).toEqual([3]);
  });
});

describe("hopsFrom", () => {
  it("counts hops up to the limit", () => {
    const graph = buildGraph(chainArtists, chainRelated);
    const hops = hopsFrom(graph, 0, 3);
    expect(Array.from(hops)).toEqual([0, 1, 1, 2, 3, -1, -1]);
  });

  it("stops at the limit", () => {
    const graph = buildGraph(chainArtists, chainRelated);
    expect(Array.from(hopsFrom(graph, 0, 1))).toEqual([0, 1, 1, -1, -1, -1, -1]);
  });

  it("walks against the direction of a row", () => {
    const graph = buildGraph(chainArtists, chainRelated);
    expect(hopsFrom(graph, 4, 3)[3]).toBe(1);
    expect(hopsFrom(graph, 6, 3)[5]).toBe(1);
  });
});

describe("shortestPath", () => {
  it("finds the fewest hops", () => {
    const graph = buildGraph(chainArtists, chainRelated);
    expect(shortestPath(graph, 0, 4)).toEqual([0, 2, 3, 4]);
  });

  it("works in either direction", () => {
    const graph = buildGraph(chainArtists, chainRelated);
    expect(shortestPath(graph, 4, 0)).toEqual([4, 3, 2, 0]);
  });

  it("returns null when there is no path", () => {
    const graph = buildGraph(chainArtists, chainRelated);
    expect(shortestPath(graph, 0, 6)).toBeNull();
  });

  it("returns the artist alone for a path to itself", () => {
    const graph = buildGraph(chainArtists, chainRelated);
    expect(shortestPath(graph, 3, 3)).toEqual([3]);
  });

  it("names the edges along a path", () => {
    const graph = buildGraph(chainArtists, chainRelated);
    const path = shortestPath(graph, 0, 4) ?? [];
    const edges = edgesAlong(graph, path);
    expect(edges).toHaveLength(3);
    edges.forEach((e, i) => {
      const ends = [graph.edgeSource[e], graph.edgeTarget[e]].sort();
      expect(ends).toEqual([path[i], path[i + 1]].sort());
    });
  });

  it("handles a long chain without recursion", () => {
    const count = 50_000;
    const many = artists(...Array.from({ length: count }, (_, i) => i + 1));
    const rows: RelatedRow[] = [];
    for (let i = 1; i < count; i += 1) rows.push([i, i + 1, 0.1]);
    const graph = buildGraph(many, rows);
    expect(shortestPath(graph, 0, count - 1)).toHaveLength(count);
  });
});

describe("relatedBySource", () => {
  it("keeps the file's directed lists, best score first", () => {
    const graph = buildGraph(chainArtists, chainRelated);
    const lists = relatedBySource(graph, chainRelated);
    expect(lists[0].map((r) => r.index)).toEqual([1, 2]);
    expect(lists[0][0].score).toBe(0.5);
    expect(lists[4]).toEqual([]);
    expect(lists[1].map((r) => r.index)).toEqual([0, 2]);
  });
});

describe("components", () => {
  it("measures connected components", () => {
    const graph = buildGraph(chainArtists, chainRelated);
    const { component, sizes } = componentSizes(graph);
    expect(sizes.sort()).toEqual([2, 5]);
    expect(component[0]).toBe(component[4]);
    expect(component[5]).toBe(component[6]);
    expect(component[0]).not.toBe(component[5]);
  });

  it("keeps the big components and drops tiny islands", () => {
    const many = artists(...Array.from({ length: 200 }, (_, i) => i + 1));
    const rows: RelatedRow[] = [];
    for (let i = 1; i < 197; i += 1) rows.push([i, i + 1, 0.1]);
    rows.push([198, 199, 0.1]);
    const graph = buildGraph(many, rows);
    const main = mainIndices(graph);
    expect(main).toHaveLength(197);
    expect(main).not.toContain(197);
    expect(main).not.toContain(199);
  });

  it("falls back to the largest component when everything is small", () => {
    const graph = buildGraph(chainArtists, chainRelated);
    expect(mainIndices(graph, 0.9)).toEqual([0, 1, 2, 3, 4]);
  });
});
