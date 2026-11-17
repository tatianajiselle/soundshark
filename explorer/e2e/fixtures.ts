import { test as base, expect, type Page } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

export interface FakeArtist {
  id: number;
  name: string;
  aliases: string[];
  nights: number;
  scene: number | null;
}

export interface FakeMap {
  version: number;
  generated_at: string;
  credits: { name: string; url: string }[];
  scenes: { id: number; label: string; size: number }[];
  artists: FakeArtist[];
  related: [number, number, number][];
}

export const shotsDir = process.env.EXPLORER_SHOTS ?? join(import.meta.dirname, "..", "test-results", "shots");
mkdirSync(shotsDir, { recursive: true });

let cached: FakeMap | undefined;
export function fakeMap(): FakeMap {
  cached ??= JSON.parse(readFileSync(join(import.meta.dirname, "..", "public", "map.json"), "utf8")) as FakeMap;
  return cached;
}

export function adjacency(map: FakeMap): Map<number, Set<number>> {
  const next = new Map<number, Set<number>>();
  for (const a of map.artists) next.set(a.id, new Set());
  for (const [s, t] of map.related) {
    next.get(s)?.add(t);
    next.get(t)?.add(s);
  }
  return next;
}

export function distance(map: FakeMap, from: number, to: number): number | null {
  const next = adjacency(map);
  const seen = new Map<number, number>([[from, 0]]);
  const queue = [from];
  while (queue.length > 0) {
    const node = queue.shift() as number;
    if (node === to) return seen.get(node) ?? null;
    for (const other of next.get(node) ?? []) {
      if (!seen.has(other)) {
        seen.set(other, (seen.get(node) ?? 0) + 1);
        queue.push(other);
      }
    }
  }
  return null;
}

export function relatedOf(map: FakeMap, id: number): string[] {
  const byId = new Map(map.artists.map((a) => [a.id, a]));
  return map.related
    .filter(([s]) => s === id)
    .sort((a, b) => b[2] - a[2])
    .map(([, t]) => byId.get(t)?.name ?? "");
}

export async function waitReady(page: Page) {
  await expect(page.locator("html")).toHaveAttribute("data-status", "ready");
}

interface Guards {
  cspViolations: string[];
  externalRequests: string[];
  pageErrors: string[];
}

export const test = base.extend<{ guards: Guards }>({
  guards: [
    async ({ page }, use) => {
      const guards: Guards = { cspViolations: [], externalRequests: [], pageErrors: [] };
      await page.addInitScript(() => {
        const seen: string[] = [];
        (window as unknown as { __csp: string[] }).__csp = seen;
        document.addEventListener("securitypolicyviolation", (event) => {
          seen.push(`${event.effectiveDirective} ${event.blockedURI}`);
        });
      });
      page.on("request", (request) => {
        const url = new URL(request.url());
        if (
          !["127.0.0.1", "localhost"].includes(url.hostname) &&
          url.protocol !== "data:" &&
          url.protocol !== "blob:"
        ) {
          guards.externalRequests.push(request.url());
        }
      });
      page.on("console", (message) => {
        if (/Content Security Policy/i.test(message.text())) guards.cspViolations.push(message.text());
      });
      page.on("pageerror", (error) => guards.pageErrors.push(error.message));
      await use(guards);
      const inPage = await page
        .evaluate(() => (window as unknown as { __csp?: string[] }).__csp ?? [])
        .catch(() => [] as string[]);
      expect([...guards.cspViolations, ...inPage], "no CSP violations").toEqual([]);
      expect(guards.externalRequests, "no requests to other hosts").toEqual([]);
      expect(guards.pageErrors, "no uncaught errors").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };
