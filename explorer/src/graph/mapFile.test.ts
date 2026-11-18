import { describe, expect, it } from "vitest";
import { MapFileError, parseMapFile } from "./mapFile";

function validMap(): Record<string, unknown> {
  return {
    version: 1,
    generated_at: "2026-11-17T04:31:00+00:00",
    credits: [{ name: "Invented Source", url: "https://example.org/" }],
    scenes: [
      { id: 3, label: "Vela / Orrin / Tamsk", size: 2 },
      { id: 5, label: "Brix", size: 1 },
    ],
    artists: [
      { id: 17, name: "Vela Moss", aliases: ["Véla Möss"], nights: 53, scene: 3 },
      { id: 42, name: "Orrin Tal", aliases: [], nights: 8, scene: 3 },
      { id: 50, name: "Brix", aliases: [], nights: 1, scene: null },
    ],
    related: [
      [17, 42, 0.012345],
      [42, 17, 0.01],
      [50, 17, 0.002],
    ],
  };
}

function errorOf(raw: unknown): string {
  try {
    parseMapFile(raw);
  } catch (error) {
    expect(error).toBeInstanceOf(MapFileError);
    return (error as Error).message;
  }
  throw new Error("expected the map to be rejected");
}

describe("parseMapFile", () => {
  it("accepts a map that follows the contract", () => {
    const map = parseMapFile(validMap());
    expect(map.version).toBe(1);
    expect(map.generatedAt).toBe("2026-11-17T04:31:00+00:00");
    expect(map.artists).toHaveLength(3);
    expect(map.artists[2].scene).toBeNull();
    expect(map.related[0]).toEqual([17, 42, 0.012345]);
    expect(map.credits[0].name).toBe("Invented Source");
  });

  it("rejects something that is not an object", () => {
    expect(errorOf(null)).toMatch(/the map must be an object/);
    expect(errorOf([])).toMatch(/the map must be an object/);
  });

  it("rejects other versions", () => {
    expect(errorOf({ ...validMap(), version: 2 })).toMatch(/unsupported map version 2/);
    expect(errorOf({ ...validMap(), version: undefined })).toMatch(/unsupported map version null/);
  });

  it("rejects a bad generated_at", () => {
    expect(errorOf({ ...validMap(), generated_at: "yesterday" })).toMatch(/generated_at/);
  });

  it("names the field that is wrong", () => {
    const map = validMap();
    (map.artists as Record<string, unknown>[])[1].nights = "8";
    expect(errorOf(map)).toBe("artists[1].nights must be a whole number");
  });

  it("rejects missing lists", () => {
    const { related: _, ...rest } = validMap();
    expect(errorOf(rest)).toBe("related must be a list");
  });

  it("rejects related rows of the wrong shape", () => {
    expect(errorOf({ ...validMap(), related: [[17, 42]] })).toMatch(/related\[0\] must be \[source, target, score\]/);
    expect(errorOf({ ...validMap(), related: [[17, 42, "high"]] })).toMatch(/score must be a number/);
  });

  it("rejects related rows that point at unknown artists or themselves", () => {
    expect(errorOf({ ...validMap(), related: [[17, 99, 0.1]] })).toMatch(/unknown artist 99/);
    expect(errorOf({ ...validMap(), related: [[98, 17, 0.1]] })).toMatch(/unknown artist 98/);
    expect(errorOf({ ...validMap(), related: [[17, 17, 0.1]] })).toMatch(/to itself/);
  });

  it("rejects duplicate ids and unknown scenes", () => {
    const dupe = validMap();
    (dupe.artists as Record<string, unknown>[])[1].id = 17;
    expect(errorOf(dupe)).toMatch(/repeats artist id 17/);
    const lost = validMap();
    (lost.artists as Record<string, unknown>[])[0].scene = 9;
    expect(errorOf(lost)).toMatch(/scene 9, which is not in scenes/);
  });

  it("rejects empty names and non-text aliases", () => {
    const blank = validMap();
    (blank.artists as Record<string, unknown>[])[0].name = "  ";
    expect(errorOf(blank)).toMatch(/name must not be empty/);
    const alias = validMap();
    (alias.artists as Record<string, unknown>[])[0].aliases = [3];
    expect(errorOf(alias)).toBe("artists[0].aliases[0] must be text");
  });
});
