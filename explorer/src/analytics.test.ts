import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type Track = (event: string, data?: Record<string, unknown>) => void;
const win = globalThis as unknown as { window?: { umami?: { track: Track } } };

async function fresh() {
  vi.resetModules();
  return import("./analytics");
}

describe("track", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    win.window = {};
  });

  afterEach(() => {
    vi.useRealTimers();
    delete win.window;
  });

  it("sends straight away when the tracker is loaded", async () => {
    const calls: unknown[] = [];
    (win.window as { umami?: { track: Track } }).umami = { track: (...args) => calls.push(args) };
    const { track } = await fresh();
    track("degree", { value: 2 });
    expect(calls).toEqual([["degree", { value: 2 }]]);
  });

  it("queues events until the tracker loads, in order", async () => {
    const calls: unknown[] = [];
    const { track } = await fresh();
    track("setup", { theme: "dark" });
    track("rendered", { ms: 900 });
    vi.advanceTimersByTime(600);
    expect(calls).toEqual([]);
    (win.window as { umami?: { track: Track } }).umami = { track: (...args) => calls.push(args) };
    vi.advanceTimersByTime(300);
    expect(calls).toEqual([
      ["setup", { theme: "dark" }],
      ["rendered", { ms: 900 }],
    ]);
  });

  it("drops the queue when the tracker never loads", async () => {
    const calls: unknown[] = [];
    const { track } = await fresh();
    track("setup");
    vi.advanceTimersByTime(20_000);
    (win.window as { umami?: { track: Track } }).umami = { track: (...args) => calls.push(args) };
    track("view", { mode: "3d" });
    expect(calls).toEqual([["view", { mode: "3d" }]]);
  });

  it("never throws when the tracker fails", async () => {
    (win.window as { umami?: { track: Track } }).umami = {
      track: () => {
        throw new Error("blocked");
      },
    };
    const { track } = await fresh();
    expect(() => track("zoom", { direction: "in" })).not.toThrow();
  });

  it("does nothing without a window", async () => {
    delete win.window;
    const { track } = await fresh();
    expect(() => track("setup")).not.toThrow();
  });
});

describe("clip", () => {
  it("trims and shortens", async () => {
    const { clip } = await fresh();
    expect(clip("  abc  ")).toBe("abc");
    expect(clip("x".repeat(100), 10)).toBe("x".repeat(10));
  });
});
