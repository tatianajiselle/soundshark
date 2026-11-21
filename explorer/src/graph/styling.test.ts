import { describe, expect, it } from "vitest";
import { buildGraph, edgesAlong, hopsFrom, shortestPath } from "./graph";
import type { Artist, RelatedRow, Scene } from "./mapFile";
import { HOP_POINT_ALPHA, THEMES, hexToRgba, pointSize, sceneColors, styleGraph } from "./styling";

describe("hexToRgba", () => {
  it("converts to 0-1 channels", () => {
    expect(hexToRgba("#ff8000", 0.5)).toEqual([1, 128 / 255, 0, 0.5]);
    expect(() => hexToRgba("red")).toThrow();
  });
});

describe("sceneColors", () => {
  const scenes: Scene[] = Array.from({ length: 16 }, (_, i) => ({
    id: 100 + i,
    label: `S${i}`,
    size: i === 15 ? 999 : 50 - i,
  }));

  it("gives the biggest scenes the palette in order and the rest grey", () => {
    const colors = sceneColors(scenes, "dark");
    const palette = THEMES.dark.scenes;
    expect(colors.get(115)).toBe(palette[0]);
    expect(colors.get(100)).toBe(palette[1]);
    expect(colors.get(110)).toBe(palette[11]);
    expect(colors.get(111)).toBe(THEMES.dark.neutral);
    expect(colors.get(114)).toBe(THEMES.dark.neutral);
  });

  it("uses distinct colours for the coloured scenes", () => {
    for (const theme of ["dark", "light"] as const) {
      const used = [...sceneColors(scenes, theme).values()].filter((c) => c !== THEMES[theme].neutral);
      expect(new Set(used).size).toBe(THEMES[theme].scenes.length);
    }
  });

  it("breaks size ties by id so colours are stable", () => {
    const tied: Scene[] = [
      { id: 9, label: "b", size: 5 },
      { id: 2, label: "a", size: 5 },
    ];
    expect(sceneColors(tied, "light").get(2)).toBe(THEMES.light.scenes[0]);
  });
});

describe("pointSize", () => {
  it("grows with the square root of nights", () => {
    expect(pointSize(0, 100)).toBe(2);
    expect(pointSize(100, 100)).toBe(12);
    expect(pointSize(25, 100)).toBeCloseTo(2 + 10 * 0.5);
    expect(pointSize(5, 0)).toBe(2);
  });
});

describe("styleGraph", () => {
  const scenes: Scene[] = [
    { id: 1, label: "one", size: 3 },
    { id: 2, label: "two", size: 2 },
  ];
  const artists: Artist[] = [
    { id: 1, name: "a", aliases: [], nights: 1, cities: [], pos: null, scene: 1 },
    { id: 2, name: "b", aliases: [], nights: 1, cities: [], pos: null, scene: 1 },
    { id: 3, name: "c", aliases: [], nights: 1, cities: [], pos: null, scene: 1 },
    { id: 4, name: "d", aliases: [], nights: 1, cities: [], pos: null, scene: 2 },
    { id: 5, name: "e", aliases: [], nights: 1, cities: [], pos: null, scene: 2 },
    { id: 6, name: "f", aliases: [], nights: 1, cities: [], pos: null, scene: null },
  ];
  const related: RelatedRow[] = [
    [1, 2, 1],
    [2, 3, 1],
    [3, 4, 1],
    [4, 5, 1],
    [5, 6, 1],
  ];
  const graph = buildGraph(artists, related);
  const sceneOf = artists.map((a) => a.scene);
  const colors = sceneColors(scenes, "dark");
  const t = THEMES.dark;

  it("colours the whole map by scene", () => {
    const styled = styleGraph(graph, sceneOf, colors, { kind: "map", scene: null, inCity: null }, "dark");
    expect(styled.pointColors[0]).toEqual(hexToRgba(t.scenes[0]));
    expect(styled.pointColors[3]).toEqual(hexToRgba(t.scenes[1]));
    expect(styled.pointColors[5]).toEqual(hexToRgba(t.neutral));
    expect(styled.linkColors[0][3]).toBe(t.mapLinkAlpha);
    expect(styled.linkColors[2][3]).toBe(t.crossLinkAlpha);
  });

  it("dims everything outside a highlighted scene", () => {
    const styled = styleGraph(graph, sceneOf, colors, { kind: "map", scene: 2, inCity: null }, "dark");
    expect(styled.pointColors[3]).toEqual(hexToRgba(t.scenes[1]));
    expect(styled.pointColors[0][3]).toBe(t.dimPointAlpha);
    expect(styled.linkColors[3][3]).toBeGreaterThan(t.mapLinkAlpha);
    expect(styled.linkColors[0][3]).toBe(t.dimLinkAlpha);
  });

  it("dims artists who never played the chosen city", () => {
    const inCity = Uint8Array.from([1, 1, 1, 0, 0, 0]);
    const styled = styleGraph(graph, sceneOf, colors, { kind: "map", scene: null, inCity }, "dark");
    expect(styled.pointColors[0]).toEqual(hexToRgba(t.scenes[0]));
    expect(styled.pointColors[3][3]).toBe(t.dimPointAlpha);
    expect(styled.linkColors[0][3]).toBe(t.mapLinkAlpha);
    expect(styled.linkColors[2][3]).toBe(t.dimLinkAlpha);
  });

  it("colours points by hop in focus mode", () => {
    const hops = hopsFrom(graph, 0, 3);
    const styled = styleGraph(graph, sceneOf, colors, { kind: "focus", focus: 0, hops }, "dark");
    expect(styled.pointColors[0]).toEqual(hexToRgba(t.hops[0]));
    expect(styled.pointColors[1]).toEqual(hexToRgba(t.hops[1]));
    expect(styled.pointColors[2]).toEqual(hexToRgba(t.hops[2], HOP_POINT_ALPHA[2]));
    expect(styled.pointColors[3]).toEqual(hexToRgba(t.hops[3], HOP_POINT_ALPHA[3]));
    expect(styled.pointColors[4][3]).toBe(t.dimPointAlpha);
    expect(styled.linkWidths[0]).toBe(2);
    expect(styled.linkColors[4][3]).toBe(t.dimLinkAlpha);
    expect([...styled.emphasis]).toEqual([0]);
  });

  it("draws the path over everything else", () => {
    const path = shortestPath(graph, 0, 5) ?? [];
    const pathEdges = edgesAlong(graph, path);
    const hops = hopsFrom(graph, 0, 3);
    const styled = styleGraph(graph, sceneOf, colors, { kind: "path", focus: 0, hops, path, pathEdges }, "dark");
    expect(styled.pointColors[0]).toEqual(hexToRgba(t.hops[0]));
    expect(styled.pointColors[5]).toEqual(hexToRgba(t.hops[0]));
    expect(styled.pointColors[2]).toEqual(hexToRgba(t.path));
    expect(Array.from(styled.linkWidths)).toEqual([4, 4, 4, 4, 4]);
    expect([...styled.emphasis]).toEqual(path);
  });
});
