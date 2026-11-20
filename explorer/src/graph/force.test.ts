import { describe, expect, it } from "vitest";
import { edgeBetween, emphasisedEdges, layoutEdges, mainMask, rgbaCss } from "./force";
import { buildGraph, edgesAlong, hopsFrom, relatedBySource, shortestPath } from "./graph";
import type { Artist, RelatedRow } from "./mapFile";
import { sceneColors, styleGraph } from "./styling";

const artists: Artist[] = [1, 2, 3, 4, 5, 6, 7].map((id) => ({
  id,
  name: `Artist ${id}`,
  aliases: [],
  nights: id,
  cities: [],
  scene: null,
}));
const rows: RelatedRow[] = [
  [1, 2, 0.9],
  [1, 3, 0.8],
  [1, 4, 0.7],
  [2, 1, 0.9],
  [2, 3, 0.5],
  [3, 4, 0.4],
  [4, 5, 0.3],
  [6, 7, 0.2],
];
const graph = buildGraph(artists, rows);
const related = relatedBySource(graph, rows);

describe("edgeBetween", () => {
  it("finds the edge either way round", () => {
    const e = edgeBetween(graph, 0, 1);
    expect(e).toBeGreaterThanOrEqual(0);
    expect(edgeBetween(graph, 1, 0)).toBe(e);
    expect(edgeBetween(graph, 0, 5)).toBe(-1);
  });
});

describe("layoutEdges", () => {
  it("keeps each artist's closest few, once per pair", () => {
    const all = new Uint8Array(graph.size).fill(1);
    const edges = layoutEdges(graph, related, all, 1);
    const pairs = edges.map((e) => [graph.edgeSource[e], graph.edgeTarget[e]]);
    expect(pairs).toContainEqual([0, 1]);
    expect(pairs.filter(([a, b]) => a === 0 && b === 1)).toHaveLength(1);
    expect(pairs).not.toContainEqual([0, 2]);
    expect(new Set(edges).size).toBe(edges.length);
  });

  it("leaves out artists that are not shown", () => {
    const mask = mainMask(graph);
    expect(Array.from(mask)).toEqual([1, 1, 1, 1, 1, 0, 0]);
    const edges = layoutEdges(graph, related, mask, 3);
    for (const e of edges) {
      expect(mask[graph.edgeSource[e]]).toBe(1);
      expect(mask[graph.edgeTarget[e]]).toBe(1);
    }
  });
});

describe("emphasisedEdges", () => {
  it("returns the path's edges that the layout does not already draw", () => {
    const path = shortestPath(graph, 0, 4) ?? [];
    const pathEdges = edgesAlong(graph, path);
    const view = { kind: "path" as const, focus: 0, hops: hopsFrom(graph, 0, 3), path, pathEdges };
    const styling = styleGraph(
      graph,
      artists.map((a) => a.scene),
      sceneColors([], "dark"),
      view,
      "dark",
    );
    const all = new Uint8Array(graph.size).fill(1);
    expect(emphasisedEdges(graph, styling, all, new Set()).sort()).toEqual([...pathEdges].sort());
    expect(emphasisedEdges(graph, styling, all, new Set([pathEdges[0]]))).not.toContain(pathEdges[0]);
  });
});

describe("rgbaCss", () => {
  it("writes 0-1 channels as css", () => {
    expect(rgbaCss([1, 0.5, 0, 0.25])).toBe("rgba(255,128,0,0.25)");
  });
});
