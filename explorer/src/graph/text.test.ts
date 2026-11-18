import { describe, expect, it } from "vitest";
import { buildSearchIndex, search } from "./search";
import { parseMapFile } from "./mapFile";
import { prepare } from "./prepare";
import { escapeHtml, formatCount, formatGenerated, formatNights } from "./text";

describe("escapeHtml", () => {
  it("escapes markup so labels show it as text", () => {
    expect(escapeHtml(`<img src=x onerror="go()"> & 'b'`)).toBe(
      "&lt;img src=x onerror=&quot;go()&quot;&gt; &amp; &#39;b&#39;",
    );
    expect(escapeHtml("Plain Name")).toBe("Plain Name");
  });
});

describe("formatting", () => {
  it("formats nights and counts", () => {
    expect(formatNights(1)).toBe("1 night");
    expect(formatNights(1234)).toBe("1,234 nights");
    expect(formatCount(1, "artist", "artists")).toBe("1 artist");
    expect(formatCount(30000, "artist", "artists")).toBe("30,000 artists");
  });

  it("formats generated_at in UTC", () => {
    expect(formatGenerated("2026-11-17T04:31:00+00:00")).toBe("17 Nov 2026, 04:31 UTC");
    expect(formatGenerated("2026-11-17T06:31:00+02:00")).toBe("17 Nov 2026, 04:31 UTC");
    expect(formatGenerated("soon")).toBe("soon");
  });
});

describe("prepare", () => {
  it("builds everything the explorer needs from a map", () => {
    const map = parseMapFile({
      version: 1,
      generated_at: "2026-11-17T04:31:00+00:00",
      credits: [],
      scenes: [{ id: 3, label: "x", size: 1 }],
      artists: [
        { id: 17, name: "Vela", aliases: [], nights: 53, scene: 3 },
        { id: 42, name: "Orrin", aliases: [], nights: 8, scene: null },
      ],
      related: [[17, 42, 0.1]],
    });
    const explorer = prepare(map);
    expect(explorer.maxNights).toBe(53);
    expect(explorer.withoutScene).toBe(1);
    expect(explorer.sceneById.get(3)?.label).toBe("x");
    expect(explorer.related[0]).toEqual([{ index: 1, score: 0.1 }]);
    expect(explorer.graph.edgeCount).toBe(1);
    expect(search(buildSearchIndex(map.artists), "orr")[0].index).toBe(1);
  });
});
