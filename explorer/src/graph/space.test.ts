import { describe, expect, it } from "vitest";
import { depth, fade, flightShot, hopFacts, pickBoxes, spread, unit } from "./space";

describe("pickBoxes", () => {
  const box = (key: string, x: number, y: number, priority: number) => ({ key, x, y, width: 40, height: 20, priority });

  it("keeps the highest priority label when two overlap", () => {
    const picked = pickBoxes([box("low", 100, 100, 1), box("high", 110, 105, 5)], 10, 500, 500);
    expect(picked.map((b) => b.key)).toEqual(["high"]);
  });

  it("keeps labels that don't overlap, up to the limit", () => {
    const many = [box("a", 50, 50, 3), box("b", 200, 50, 2), box("c", 350, 50, 1)];
    expect(pickBoxes(many, 2, 500, 500).map((b) => b.key)).toEqual(["a", "b"]);
  });

  it("drops labels that would be cut off at the edge", () => {
    expect(pickBoxes([box("edge", 5, 100, 9)], 10, 500, 500)).toEqual([]);
  });
});

describe("geometry", () => {
  it("measures depth along the view direction", () => {
    const eye = { x: 0, y: 0, z: 10 };
    const forward = { x: 0, y: 0, z: -1 };
    expect(depth({ x: 0, y: 0, z: 0 }, eye, forward)).toBe(10);
    expect(depth({ x: 0, y: 0, z: 20 }, eye, forward)).toBe(-10);
  });

  it("fades between full and gone", () => {
    expect(fade(5, 10, 20)).toBe(1);
    expect(fade(15, 10, 20)).toBe(0.5);
    expect(fade(25, 10, 20)).toBe(0);
  });

  it("uses the 90th percentile radius as the map's spread", () => {
    const points = Array.from({ length: 10 }, (_, i) => ({ x: i + 1, y: 0, z: 0 }));
    expect(spread(points)).toBe(9);
    expect(spread([])).toBe(1);
  });
});

describe("unit", () => {
  it("normalises vectors, with a safe zero case", () => {
    expect(unit({ x: 3, y: 0, z: 4 })).toEqual({ x: 0.6, y: 0, z: 0.8 });
    expect(unit({ x: 0, y: 0, z: 0 })).toEqual({ x: 0, y: 0, z: 1 });
  });
});

describe("flightShot", () => {
  it("sits behind the stop, looking towards the next one", () => {
    const shot = flightShot(null, { x: 0, y: 0, z: 0 }, { x: 10, y: 0, z: 0 }, 100);
    expect(shot.x).toBe(-100);
    expect(shot.y).toBeCloseTo(35);
  });

  it("keeps the last heading at the final stop", () => {
    const shot = flightShot({ x: 0, y: 0, z: 0 }, { x: 0, y: 0, z: 10 }, null, 100);
    expect(shot.z).toBe(-90);
  });
});

describe("hopFacts", () => {
  it("lists shared cities and each side's rank of the other", () => {
    const facts = hopFacts(
      ["Lakeport", "Northvale"],
      ["Northvale"],
      [{ index: 7 }, { index: 2 }],
      [{ index: 1 }],
      1,
      2,
    );
    expect(facts).toEqual({ sharedCities: ["Northvale"], rankFromA: 2, rankFromB: 1 });
  });

  it("says null when one isn't in the other's list", () => {
    expect(hopFacts([], [], [], [], 1, 2)).toEqual({ sharedCities: [], rankFromA: null, rankFromB: null });
  });
});
