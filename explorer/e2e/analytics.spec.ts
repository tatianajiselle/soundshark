import type { Page } from "@playwright/test";
import { distance, expect, fakeMap, relatedOf, test, waitReady, type FakeArtist } from "./fixtures";

type Sent = [string, Record<string, unknown> | undefined];

const map = fakeMap();
const rowsFrom = (id: number) => map.related.filter(([s]) => s === id).length;
const mainland = map.artists.slice(0, -3);
const subject = mainland.find((a) => a.nights >= 10 && a.nights <= 40 && rowsFrom(a.id) === 10) as FakeArtist;
const far = mainland.find((a) => (distance(map, subject.id, a.id) ?? 0) >= 3) as FakeArtist;

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const sent: [string, unknown][] = [];
    (window as unknown as { __sent: typeof sent }).__sent = sent;
    window.setTimeout(() => {
      (window as unknown as { umami: { track: (e: string, d?: unknown) => void } }).umami = {
        track: (event, data) => sent.push([event, data]),
      };
    }, 300);
    window.addEventListener("click", (event) => {
      if (event.target instanceof Element && event.target.closest("a[target='_blank']")) event.preventDefault();
    });
  });
});

async function sent(page: Page): Promise<Sent[]> {
  return page.evaluate(() => (window as unknown as { __sent: Sent[] }).__sent);
}

async function expectEvent(page: Page, name: string, data?: Record<string, unknown>) {
  await expect
    .poll(async () => (await sent(page)).filter(([event]) => event === name).map(([, d]) => d ?? {}))
    .toContainEqual(data ? expect.objectContaining(data) : expect.anything());
}

test.describe("analytics", () => {
  test.use({ welcomed: false });

  test("queues events until the tracker loads and records the visit setup", async ({ page }) => {
    await page.goto("/");
    await waitReady(page);
    await expectEvent(page, "setup", { view: "2d", deepLink: false, city: "All" });
    await expectEvent(page, "rendered", { view: "2d" });
    await page.getByTestId("welcome-start").click();
    await expectEvent(page, "welcome-close");
    await page.getByTestId("open-welcome").click();
    await expectEvent(page, "welcome-open");
    await page.keyboard.press("Escape");
    expect((await sent(page)).filter(([e]) => e === "welcome-close")).toHaveLength(2);
  });

  test.describe("returning visitor", () => {
    test.use({ welcomed: true });

    test("records searches, misses, picks and the panel", async ({ page }) => {
      await page.goto("/");
      await waitReady(page);
      const search = page.getByRole("combobox", { name: "Search artists" });
      await search.fill("zzqxj");
      await expectEvent(page, "search-miss", { box: "search", query: "zzqxj" });
      await search.fill(subject.name);
      await page
        .getByRole("option", { name: new RegExp(subject.name) })
        .first()
        .click();
      await expectEvent(page, "search-pick", { box: "search", query: subject.name, name: subject.name, rank: 1 });
      await expectEvent(page, "artist", { name: subject.name, from: "search" });

      await page.getByTestId("degree-2").click();
      await expectEvent(page, "degree", { value: 2, name: subject.name });
      await page.getByTestId("degree-1").click();
      const names = relatedOf(map, subject.id);
      await page.getByTestId("related").getByRole("button", { name: names[1] }).click();
      await expectEvent(page, "artist", { name: names[1], from: "related", degree: 1, rank: 2 });

      await page.keyboard.press("Escape");
      await expectEvent(page, "close-artist", { name: names[1], via: "escape" });
      await page.keyboard.press("/");
      await expectEvent(page, "shortcut", { key: "/" });
    });

    test("records paths, clearing them, cities, scenes, view, zoom, about and links", async ({ page }) => {
      await page.goto(`/#a=${subject.id}`);
      await waitReady(page);
      await expectEvent(page, "setup", { deepLink: true });
      const connect = page.getByRole("combobox", { name: "Connect to another artist" });
      await connect.fill(far.name);
      await page
        .getByRole("option", { name: new RegExp(far.name) })
        .first()
        .click();
      const hops = distance(map, subject.id, far.id) as number;
      await expectEvent(page, "search-pick", { box: "connect-search", name: far.name });
      await expectEvent(page, "path", { from: subject.name, to: far.name, steps: hops });
      await page.getByRole("button", { name: "Clear the path" }).click();
      await expectEvent(page, "clear-path", { name: subject.name });
      await page.getByRole("button", { name: "Back to the whole map" }).click();
      await expectEvent(page, "close-artist", { name: subject.name, via: "button" });

      await page.getByTestId("cities").getByRole("radio", { name: "Northvale" }).click();
      await expectEvent(page, "city", { name: "Northvale" });
      await page.getByTestId("cities").getByRole("radio", { name: "All" }).click();
      await expectEvent(page, "city", { name: "All" });

      await page.getByTestId("legend").locator(".legend-scene").nth(1).click();
      await expectEvent(page, "scene", { name: map.scenes[1].label });

      await page.getByTestId("zoom-in").click();
      await expectEvent(page, "zoom", { direction: "in" });
      await page.getByTestId("zoom-out").click();
      await expectEvent(page, "zoom", { direction: "out" });

      const footer = page.getByTestId("footer");
      const credit = map.credits[0];
      await footer.getByRole("link", { name: credit.name }).click();
      await expectEvent(page, "link", { to: new URL(credit.url).hostname.replace(/^www\./, "") });
      await footer.getByRole("button", { name: "About" }).click();
      await expectEvent(page, "about-open");
      await page.keyboard.press("Escape");

      await page.getByTestId("mode-toggle").click();
      await expectEvent(page, "view", { mode: "3d" });
    });

    test("records an artist picked on the map", async ({ page }) => {
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.goto("/");
      await waitReady(page);
      const box = (await page.getByTestId("map").boundingBox()) as {
        x: number;
        y: number;
        width: number;
        height: number;
      };
      const hover = page.locator(".map-label-hover");
      const panel = page.getByTestId("panel");
      const cx = box.x + box.width / 2;
      const cy = box.y + box.height / 2;
      for (let step = 0; step < 300 && (await panel.count()) === 0; step += 1) {
        const x = cx + Math.cos(step * 0.7) * (4 + step * 1.2);
        const y = cy + Math.sin(step * 0.7) * (4 + step * 1.2);
        await page.mouse.move(x, y);
        await page.waitForTimeout(80);
        if ((await hover.count()) === 0 || !(await hover.first().isVisible())) continue;
        await page.mouse.click(x, y);
        await page.waitForTimeout(300);
      }
      const name = ((await panel.getByRole("heading", { level: 2 }).textContent()) ?? "").trim();
      await expectEvent(page, "artist", { name, from: "map" });
    });

    test("records an unknown artist in the address", async ({ page }) => {
      await page.goto("/#a=999999");
      await waitReady(page);
      await expectEvent(page, "missing-artist", { id: "999999" });
    });
  });
});

test.describe("analytics in 3D", () => {
  test.use({ view: "3d" });

  test("records flying a path and stopping", async ({ page }) => {
    await page.goto(`/#a=${subject.id}&b=${far.id}`);
    await waitReady(page);
    await expect(page.locator("html")).toHaveAttribute("data-layout3d", "settled", { timeout: 60_000 });
    const hops = distance(map, subject.id, far.id) as number;
    await page.getByTestId("fly-path").click();
    await expectEvent(page, "fly", { from: subject.name, to: far.name, steps: hops });
    await page.getByTestId("flight-stop").click();
    await expectEvent(page, "fly-stop", { of: hops + 1 });
  });
});
