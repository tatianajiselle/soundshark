import { describe, expect, it } from "vitest";
import { placeLabels } from "./labels";

describe("placeLabels", () => {
  it("puts a label just above its point", () => {
    const [label] = placeLabels([{ index: 3, x: 100, y: 200, text: "Vela" }]);
    expect(label.left + label.width / 2).toBe(100);
    expect(label.top + label.height).toBeLessThan(200);
  });

  it("moves labels apart when points sit on top of each other", () => {
    const labels = placeLabels([
      { index: 1, x: 100, y: 200, text: "Vela Moss" },
      { index: 2, x: 104, y: 201, text: "Orrin Tal" },
      { index: 3, x: 98, y: 199, text: "Brix" },
    ]);
    expect(labels).toHaveLength(3);
    for (let i = 0; i < labels.length; i += 1) {
      for (let j = i + 1; j < labels.length; j += 1) {
        const a = labels[i];
        const b = labels[j];
        const apart = a.top + a.height <= b.top || b.top + b.height <= a.top;
        expect(apart).toBe(true);
      }
    }
  });

  it("leaves labels that do not touch where they are", () => {
    const labels = placeLabels([
      { index: 1, x: 100, y: 100, text: "A" },
      { index: 2, x: 400, y: 100, text: "B" },
    ]);
    expect(labels[0].top).toBe(labels[1].top);
  });

  it("keeps labels inside the map", () => {
    const [left, right] = placeLabels(
      [
        { index: 1, x: 2, y: 100, text: "A long name on the left" },
        { index: 2, x: 398, y: 300, text: "A long name on the right" },
      ],
      400,
    );
    expect(left.left).toBeGreaterThanOrEqual(4);
    expect(right.left + right.width).toBeLessThanOrEqual(396);
  });
});
