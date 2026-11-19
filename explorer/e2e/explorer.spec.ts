import type { Page } from "@playwright/test";
import { join } from "node:path";
import { distance, expect, fakeMap, relatedOf, shotsDir, test, waitReady, type FakeArtist } from "./fixtures";

const map = fakeMap();
const rowsFrom = (id: number) => map.related.filter(([s]) => s === id).length;
const mainland = map.artists.slice(0, -3);
const subject = mainland.find((a) => a.nights >= 10 && a.nights <= 40 && rowsFrom(a.id) === 10) as FakeArtist;
const far = mainland.find((a) => (distance(map, subject.id, a.id) ?? 0) >= 3) as FakeArtist;
const island = map.artists[map.artists.length - 1];
const aliased = map.artists.find((a) => a.aliases.includes("Ćevrà Dœlmüth")) as FakeArtist;

async function nonBackgroundShare(page: Page): Promise<number> {
  const hide = ".css-label--label, .path-labels, .topbar, .legend, .footer, .panel, [class*='attribution']";
  await page.evaluate((selector) => {
    document.querySelectorAll<HTMLElement>(selector).forEach((el) => (el.style.visibility = "hidden"));
  }, hide);
  const png = await page.getByTestId("map").screenshot();
  await page.evaluate((selector) => {
    document.querySelectorAll<HTMLElement>(selector).forEach((el) => (el.style.visibility = ""));
  }, hide);
  return page.evaluate(async (base64) => {
    const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
    const bitmap = await createImageBitmap(new Blob([bytes], { type: "image/png" }));
    const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
    const context = canvas.getContext("2d") as OffscreenCanvasRenderingContext2D;
    context.drawImage(bitmap, 0, 0);
    const { data } = context.getImageData(0, 0, bitmap.width, bitmap.height);
    const [r0, g0, b0] = [data[0], data[1], data[2]];
    let different = 0;
    for (let i = 0; i < data.length; i += 4) {
      if (Math.abs(data[i] - r0) + Math.abs(data[i + 1] - g0) + Math.abs(data[i + 2] - b0) > 40) different += 1;
    }
    return different / (data.length / 4);
  }, png.toString("base64"));
}

test.describe("whole map", () => {
  test("loads, draws the graph and lists the scenes", async ({ page }) => {
    await page.goto("/");
    await waitReady(page);
    await expect(page.locator(".map canvas").first()).toBeVisible();
    await expect.poll(() => nonBackgroundShare(page), { timeout: 60_000 }).toBeGreaterThan(0.005);

    const legend = page.getByTestId("legend");
    const scenes = legend.locator(".legend-scene");
    await expect(scenes).toHaveCount(map.scenes.length);
    await expect(scenes.first()).toContainText(map.scenes[0].label);
    await expect(scenes.first()).toContainText(map.scenes[0].size.toLocaleString("en-GB"));
    const withoutScene = map.artists.filter((a) => a.scene === null).length;
    await expect(legend).toContainText(`${withoutScene} artists without a scene`);

    await scenes.nth(1).click();
    await expect(scenes.nth(1)).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: "Show all scenes" })).toBeVisible();
    await page.waitForTimeout(1500);
    await page.screenshot({ path: join(shotsDir, "desktop-scene-highlight.png") });
    await page.keyboard.press("Escape");
    await expect(scenes.nth(1)).toHaveAttribute("aria-pressed", "false");
    await page.waitForTimeout(2500);
    await page.screenshot({ path: join(shotsDir, "desktop-whole-map.png") });
  });

  test("shows one city at a time and keeps it in the link", async ({ page }) => {
    await page.goto("/");
    await waitReady(page);
    const cities = page.getByTestId("cities");
    await expect(cities.getByRole("radio")).toHaveText(["All", "Lakeport", "Northvale"]);
    await expect(cities.getByRole("radio", { name: "All" })).toHaveAttribute("aria-checked", "true");

    await cities.getByRole("radio", { name: "Northvale" }).click();
    await expect(cities.getByRole("radio", { name: "Northvale" })).toHaveAttribute("aria-checked", "true");
    await expect(page).toHaveURL(/#c=Northvale$/);
    await page.waitForTimeout(1500);
    await page.screenshot({ path: join(shotsDir, "desktop-one-city.png") });

    await page.reload();
    await waitReady(page);
    await expect(cities.getByRole("radio", { name: "Northvale" })).toHaveAttribute("aria-checked", "true");
    await cities.getByRole("radio", { name: "All" }).click();
    await expect(page).not.toHaveURL(/#/);
  });

  test("switches to the 3D view and back", async ({ page }) => {
    await page.goto("/");
    await waitReady(page);
    const toggle = page.getByTestId("mode-toggle");
    await expect(toggle).toHaveAttribute("aria-pressed", "false");

    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("map-3d").locator("canvas")).toBeVisible();
    await expect(page.getByTestId("cities")).toHaveCount(0);
    await expect(page.locator("html")).toHaveAttribute("data-layout3d", "settled", { timeout: 20_000 });
    await page.screenshot({ path: join(shotsDir, "desktop-3d.png") });

    await toggle.click();
    await expect(page.getByTestId("map-3d")).toHaveCount(0);
    await expect(page.getByTestId("cities")).toBeVisible();
  });

  test("shows the credits from the file and the about text", async ({ page }) => {
    await page.goto("/");
    await waitReady(page);
    const footer = page.getByTestId("footer");
    await expect(footer).toContainText("Connections are derived from public lineups");
    await expect(footer).toContainText("17 Nov 2026, 04:31 UTC");
    for (const credit of map.credits) {
      const link = footer.getByRole("link", { name: credit.name });
      await expect(link).toHaveAttribute("href", credit.url);
      await expect(link).toHaveAttribute("rel", "noopener noreferrer");
    }
    await footer.getByRole("button", { name: "About" }).click();
    const about = page.getByTestId("about");
    await expect(about).toBeVisible();
    await expect(about).toContainText("CC BY-NC 4.0");
    await expect(about).toContainText(`${map.artists.length.toLocaleString("en-GB")} artists`);
    await page.keyboard.press("Escape");
    await expect(about).toBeHidden();
  });
});

test.describe("search and focus", () => {
  test("finds an artist by an accented alias typed without accents", async ({ page }) => {
    await page.goto("/");
    await waitReady(page);
    const input = page.getByRole("combobox", { name: "Search artists" });
    await input.fill("cevra doelm");
    const option = page.getByRole("option").first();
    await expect(option).toContainText(aliased.name);
    await expect(option).toContainText("also listed as Ćevrà Dœlmüth");
    await input.press("ArrowDown");
    await input.press("ArrowUp");
    await input.press("Enter");
    const panel = page.getByTestId("panel");
    await expect(panel.getByRole("heading", { level: 2 })).toHaveText(aliased.name);
    await expect(panel).toContainText("Also listed as Ćevrà Dœlmüth");
    await expect(page).toHaveURL(new RegExp(`#a=${aliased.id}$`));
  });

  test("moves through results with the keyboard and closes them with Escape", async ({ page }) => {
    await page.goto("/");
    await waitReady(page);
    const input = page.getByRole("combobox", { name: "Search artists" });
    await input.fill(subject.name.slice(0, 3));
    const options = page.getByRole("option");
    await expect(options.first()).toBeVisible();
    await input.press("ArrowDown");
    await expect(options.nth(1)).toHaveAttribute("aria-selected", "true");
    await input.press("Escape");
    await expect(options).toHaveCount(0);
    await expect(input).toHaveValue("");
    await expect(page.getByTestId("panel")).toHaveCount(0);
  });

  test("focus shows the artist and its related list, and a related entry refocuses", async ({ page }) => {
    await page.goto(`/#a=${subject.id}`);
    await waitReady(page);
    const panel = page.getByTestId("panel");
    await expect(panel.getByRole("heading", { level: 2 })).toHaveText(subject.name);
    await expect(panel).toContainText(`${subject.nights} nights`);
    const scene = map.scenes.find((s) => s.id === subject.scene);
    await expect(panel).toContainText(scene ? scene.label : "No scene");
    const names = relatedOf(map, subject.id);
    const entries = page.getByTestId("related").locator(".related-name");
    await expect(entries).toHaveText(names);
    await expect(page.getByTestId("legend")).toContainText("1 hop away");
    await page.waitForTimeout(3000);
    await page.screenshot({ path: join(shotsDir, "desktop-focus.png") });

    await page.getByTestId("related").getByRole("button", { name: names[1] }).click();
    await expect(panel.getByRole("heading", { level: 2 })).toHaveText(names[1]);
    const second = map.artists.find((a) => a.name === names[1]) as FakeArtist;
    await expect(page).toHaveURL(new RegExp(`#a=${second.id}$`));

    await page.goBack();
    await expect(panel.getByRole("heading", { level: 2 })).toHaveText(subject.name);

    await page.keyboard.press("Escape");
    await expect(panel).toHaveCount(0);
    await expect(page).toHaveURL(/\/$/);
  });

  test("clicking a point on the map focuses that artist", async ({ page }) => {
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
    await page.mouse.click(box.x + 6, box.y + box.height - 60);
    await page.waitForTimeout(500);
    await expect(panel, "a click on empty space does nothing").toHaveCount(0);

    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    let hovered = "";
    for (let step = 0; step < 300 && (await panel.count()) === 0; step += 1) {
      const angle = step * 0.7;
      const radius = 4 + step * 1.2;
      const x = cx + Math.cos(angle) * radius;
      const y = cy + Math.sin(angle) * radius;
      await page.mouse.move(x, y);
      await page.waitForTimeout(80);
      if ((await hover.count()) === 0 || !(await hover.first().isVisible())) continue;
      hovered = (await hover.first().textContent())?.trim() ?? "";
      await page.mouse.click(x, y);
      await page.waitForTimeout(300);
    }
    const heading = panel.getByRole("heading", { level: 2 });
    await expect(heading).toBeVisible();
    const name = ((await heading.textContent()) ?? "").trim();
    const artist = map.artists.find((a) => a.name === name);
    expect(artist, `focused an artist from the map (hovered ${hovered})`).toBeDefined();
    await expect(page).toHaveURL(new RegExp(`#a=${(artist as FakeArtist).id}$`));
  });
});

test.describe("paths and the address", () => {
  test("connects two artists along a shortest path", async ({ page }) => {
    await page.goto(`/#a=${subject.id}`);
    await waitReady(page);
    const connect = page.getByRole("combobox", { name: "Connect to another artist" });
    await connect.fill(far.name);
    await page
      .getByRole("option", { name: new RegExp(far.name) })
      .first()
      .click();
    const path = page.getByTestId("path");
    const steps = path.locator(".path-steps li");
    const hops = distance(map, subject.id, far.id) as number;
    await expect(steps).toHaveCount(hops + 1);
    await expect(steps.first()).toHaveText(subject.name);
    await expect(steps.last()).toContainText(far.name);
    await expect(path).toContainText(`${hops} steps apart`);
    const names = (await steps.allTextContents()).map((t) => t.replace("→", "").trim());
    const byName = new Map(map.artists.map((a) => [a.name, a.id]));
    for (let i = 0; i + 1 < names.length; i += 1) {
      expect(distance(map, byName.get(names[i]) as number, byName.get(names[i + 1]) as number)).toBe(1);
    }
    await expect(page).toHaveURL(new RegExp(`#a=${subject.id}&b=${far.id}$`));
    await page.waitForTimeout(3000);
    await page.screenshot({ path: join(shotsDir, "desktop-path.png") });

    await page.reload();
    await waitReady(page);
    await expect(page.getByTestId("panel").getByRole("heading", { level: 2 })).toHaveText(subject.name);
    await expect(page.getByTestId("path").locator(".path-steps li")).toHaveCount(hops + 1);

    await page.getByRole("button", { name: "Clear the path" }).click();
    await expect(page).toHaveURL(new RegExp(`#a=${subject.id}$`));
  });

  test("says when there is no path within the map", async ({ page }) => {
    await page.goto(`/#a=${subject.id}&b=${island.id}`);
    await waitReady(page);
    await expect(page.getByTestId("path")).toContainText(
      `No path within the map between ${subject.name} and ${island.name}`,
    );
  });

  test("ignores an address that names an unknown artist", async ({ page }) => {
    await page.goto("/#a=999999999");
    await waitReady(page);
    await expect(page.getByTestId("panel")).toHaveCount(0);
    await expect(page.getByText("That artist isn’t in this map.")).toBeVisible();
  });
});

test.describe("phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test("fits the screen without horizontal scrolling", async ({ page }) => {
    await page.goto("/");
    await waitReady(page);
    const overflow = () =>
      page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(await overflow()).toBeLessThanOrEqual(0);
    await page.waitForTimeout(2500);
    await page.screenshot({ path: join(shotsDir, "phone-whole-map.png") });

    await page.goto(`/#a=${subject.id}&b=${far.id}`);
    await waitReady(page);
    const panel = page.getByTestId("panel");
    await expect(panel).toBeVisible();
    const box = (await panel.boundingBox()) as { x: number; width: number; y: number; height: number };
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(390);
    expect(box.y + box.height).toBeLessThanOrEqual(845);
    expect(await overflow()).toBeLessThanOrEqual(0);
    await page.waitForTimeout(2500);
    await page.screenshot({ path: join(shotsDir, "phone-path.png") });
  });
});

test.describe("light mode", () => {
  test.use({ colorScheme: "light" });

  test("draws on a light background", async ({ page }) => {
    await page.goto(`/#a=${subject.id}`);
    await waitReady(page);
    const background = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    expect(background).toBe("rgb(246, 247, 249)");
    await expect.poll(() => nonBackgroundShare(page), { timeout: 60_000 }).toBeGreaterThan(0.005);
    await page.waitForTimeout(2500);
    await page.screenshot({ path: join(shotsDir, "light-focus.png") });
  });
});
