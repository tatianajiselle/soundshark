import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import { buildGraph, shortestPath } from "../src/graph/graph";
import { parseMapFile } from "../src/graph/mapFile";

const dir = mkdtempSync(join(tmpdir(), "fake-map-"));
const script = join(import.meta.dirname, "fake-map.mjs");

function generate(name: string, ...args: string[]): unknown {
  const out = join(dir, name);
  execFileSync(process.execPath, [script, "--out", out, ...args], { stdio: "pipe" });
  return JSON.parse(readFileSync(out, "utf8"));
}

afterAll(() => rmSync(dir, { recursive: true, force: true }));

describe("fake-map.mjs", () => {
  const raw = generate("a.json", "--artists", "800");
  const map = parseMapFile(raw);

  it("writes a map that follows the contract", () => {
    expect(map.artists).toHaveLength(800);
    expect(map.scenes.length).toBeGreaterThanOrEqual(15);
    const sizes = map.scenes.map((s) => s.size);
    expect([...sizes].sort((a, b) => b - a)).toEqual(sizes);
  });

  it("is deterministic for a seed and changes with it", () => {
    expect(generate("b.json", "--artists", "800")).toEqual(raw);
    expect(generate("c.json", "--artists", "800", "--seed", "5")).not.toEqual(raw);
  });

  it("orders related rows by source and gives at most ten per artist", () => {
    const sources = map.related.map((r) => r[0]);
    expect([...sources].sort((a, b) => a - b)).toEqual(sources);
    const counts = new Map<number, number>();
    for (const [s] of map.related) counts.set(s, (counts.get(s) ?? 0) + 1);
    expect(Math.max(...counts.values())).toBeLessThanOrEqual(10);
  });

  it("plants null scenes, accented aliases and an island", () => {
    expect(map.artists.some((a) => a.scene === null)).toBe(true);
    expect(map.artists.some((a) => a.aliases.includes("Ćevrà Dœlmüth"))).toBe(true);
    const graph = buildGraph(map.artists, map.related);
    expect(shortestPath(graph, 0, graph.size - 1)).toBeNull();
  });

  it("skews how often artists are listed", () => {
    const inbound = new Map<number, number>();
    for (const [, t] of map.related) inbound.set(t, (inbound.get(t) ?? 0) + 1);
    const counts = [...inbound.values()].sort((a, b) => b - a);
    expect(counts[0]).toBeGreaterThan(counts[Math.floor(counts.length / 2)] * 5);
  });
});
