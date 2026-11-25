import { describe, expect, it } from "vitest";
import { relatedAtDegree } from "./degrees";

const list = (...pairs: [number, number][]) => pairs.map(([index, score]) => ({ index, score }));

const related = [
  list([1, 10], [2, 5]),
  list([3, 8], [0, 4], [4, 2]),
  list([4, 6], [5, 6]),
  list([6, 1]),
  list([7, 3]),
  list(),
  list(),
  list(),
];

describe("relatedAtDegree", () => {
  it("lists only artists first reached at that step, never the focus or nearer ones", () => {
    const second = relatedAtDegree(related, 0, 2, 10);
    expect(second.entries.map((e) => e.index).sort()).toEqual([3, 4, 5]);
    const third = relatedAtDegree(related, 0, 3, 10);
    expect(third.entries.map((e) => e.index).sort()).toEqual([6, 7]);
  });

  it("adds up the strength of every route and names the strongest one", () => {
    const second = relatedAtDegree(related, 0, 2, 10);
    const four = second.entries.find((e) => e.index === 4);
    expect(four?.score).toBeCloseTo(1 * (2 / 8) + 0.5 * (6 / 6));
    expect(four?.via).toBe(2);
    expect(second.entries[0].index).toBe(3);
    expect(second.entries[0].via).toBe(1);
  });

  it("keeps the top entries but reports the full count", () => {
    const second = relatedAtDegree(related, 0, 2, 2);
    expect(second.entries).toHaveLength(2);
    expect(second.total).toBe(3);
  });

  it("is empty when nothing is that far out", () => {
    expect(relatedAtDegree(related, 5, 2, 10)).toEqual({ entries: [], total: 0 });
  });
});
