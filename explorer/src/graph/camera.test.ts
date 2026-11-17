import { describe, expect, it } from "vitest";
import { boundsOf, closestStep, framingBox, insetsFrom } from "./camera";

function project(box: [number, number, number, number], width: number, height: number, yUp: boolean) {
  const scale = width / (box[2] - box[0]);
  return (x: number, y: number) => [
    (x - box[0]) * scale,
    yUp ? (box[3] - y) * (height / (box[3] - box[1])) : (y - box[1]) * (height / (box[3] - box[1])),
  ];
}

describe("boundsOf", () => {
  it("covers the chosen points and skips missing ones", () => {
    const positions = [0, 0, 10, 5, -4, 2, NaN, NaN];
    expect(boundsOf(positions, [0, 1, 3])).toEqual({ minX: 0, minY: 0, maxX: 10, maxY: 5 });
    expect(boundsOf(positions, [2])).toEqual({ minX: -4, minY: 2, maxX: -4, maxY: 2 });
    expect(boundsOf(positions, [3])).toBeNull();
  });
});

describe("framingBox", () => {
  const bounds = { minX: 0, minY: 0, maxX: 100, maxY: 50 };

  it("keeps the canvas shape so the box fills it exactly", () => {
    const box = framingBox(bounds, 1000, 500, { left: 0, top: 0, right: 0, bottom: 0 }, 0, true);
    expect((box[2] - box[0]) / (box[3] - box[1])).toBeCloseTo(2);
    expect(box).toEqual([0, 0, 100, 50]);
  });

  for (const yUp of [true, false]) {
    it(`centres the points in the uncovered area (y ${yUp ? "up" : "down"})`, () => {
      const insets = { left: 400, top: 100, right: 0, bottom: 40 };
      const box = framingBox(bounds, 1400, 900, insets, 0.1, yUp);
      const toScreen = project(box, 1400, 900, yUp);
      const [x1, y1] = toScreen(bounds.minX, yUp ? bounds.maxY : bounds.minY);
      const [x2, y2] = toScreen(bounds.maxX, yUp ? bounds.minY : bounds.maxY);
      expect((x1 + x2) / 2).toBeCloseTo(400 + 1000 / 2);
      expect((y1 + y2) / 2).toBeCloseTo(100 + 760 / 2);
      expect(x1).toBeGreaterThanOrEqual(400);
      expect(x2).toBeLessThanOrEqual(1400);
      expect(Math.min(y1, y2)).toBeGreaterThanOrEqual(100);
      expect(Math.max(y1, y2)).toBeLessThanOrEqual(860);
    });
  }
});

describe("insetsFrom", () => {
  const container = { left: 0, top: 0, right: 1400, bottom: 900 };

  it("turns side cards into side insets and wide bars into top or bottom insets", () => {
    const insets = insetsFrom(container, [
      { left: 12, top: 12, right: 412, bottom: 100 },
      { left: 12, top: 500, right: 312, bottom: 860 },
      { left: 0, top: 870, right: 1400, bottom: 900 },
    ]);
    expect(insets).toEqual({ left: 420, top: 0, right: 0, bottom: 38 });
  });

  it("ignores overlays outside the map and caps each side", () => {
    const insets = insetsFrom({ left: 0, top: 0, right: 1000, bottom: 900 }, [
      { left: 1020, top: 12, right: 1388, bottom: 860 },
      { left: 0, top: 0, right: 1000, bottom: 700 },
    ]);
    expect(insets.right).toBe(0);
    expect(insets.top).toBe(540);
  });
});

describe("closestStep", () => {
  it("finds the shortest step along a path", () => {
    const positions = [0, 0, 100, 0, 103, 4, 200, 0];
    expect(closestStep(positions, [0, 1, 2, 3])).toEqual({ distance: 5 });
    expect(closestStep(positions, [0])).toBeNull();
  });
});

describe("framingBox with a close pair", () => {
  const bounds = { minX: 0, minY: 0, maxX: 100, maxY: 50 };
  const none = { left: 0, top: 0, right: 0, bottom: 0 };
  const widthOf = (box: number[]) => box[2] - box[0];

  it("zooms in so a close pair separates, up to a limit", () => {
    const plain = framingBox(bounds, 1000, 500, none, 0, true);
    const near = framingBox(bounds, 1000, 500, none, 0, true, {
      pair: { distance: 4 },
      pixels: 60,
      maxBoost: 3,
    });
    expect(widthOf(plain) / widthOf(near)).toBeCloseTo(1.5);
    const tight = framingBox(bounds, 1000, 500, none, 0, true, {
      pair: { distance: 0.5 },
      pixels: 60,
      maxBoost: 3,
    });
    expect(widthOf(plain) / widthOf(tight)).toBeCloseTo(3);
  });

  it("leaves a fit alone when the pair is already far enough apart", () => {
    const plain = framingBox(bounds, 1000, 500, none, 0, true);
    const apart = framingBox(bounds, 1000, 500, none, 0, true, {
      pair: { distance: 40 },
      pixels: 60,
      maxBoost: 3,
    });
    expect(apart).toEqual(plain);
  });
});
