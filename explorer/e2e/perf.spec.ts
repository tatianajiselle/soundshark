import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, shotsDir, test, waitReady } from "./fixtures";

const sizes = (process.env.EXPLORER_PERF ?? "")
  .split(",")
  .map((s) => Number.parseInt(s, 10))
  .filter((n) => Number.isInteger(n) && n > 0);

test.describe("load time", () => {
  test.skip(sizes.length === 0, "set EXPLORER_PERF=6000,30000 to measure");
  test.setTimeout(900_000);

  for (const size of sizes) {
    test(`${size} artists`, async ({ page }) => {
      const dir = mkdtempSync(join(tmpdir(), "explorer-perf-"));
      const file = join(dir, "map.json");
      execFileSync(process.execPath, [
        join(import.meta.dirname, "..", "scripts", "fake-map.mjs"),
        "--artists",
        String(size),
        "--out",
        file,
      ]);
      const body = readFileSync(file);
      rmSync(dir, { recursive: true, force: true });
      await page.route("**/map.json", (route) => route.fulfill({ status: 200, contentType: "application/json", body }));

      await page.goto("/");
      await waitReady(page);
      const marks = await page.evaluate(() =>
        Object.fromEntries(performance.getEntriesByType("mark").map((m) => [m.name, Math.round(m.startTime)])),
      );
      const searchMs = await page.evaluate(async () => {
        const input = document.querySelector<HTMLInputElement>("input[role=combobox]");
        if (!input) return -1;
        const started = performance.now();
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
        setter?.call(input, "ka");
        input.dispatchEvent(new Event("input", { bubbles: true }));
        await Promise.resolve();
        return Math.round(performance.now() - started);
      });
      const summary = `${size} artists (${(body.length / 1e6).toFixed(1)} MB map): map parsed ${marks["explorer:map-parsed"]} ms, prepared ${marks["explorer:prepared"]} ms, first render ${marks["explorer:rendered"]} ms after navigation; search keystroke ${searchMs} ms`;
      console.log(summary);
      test.info().annotations.push({ type: "performance", description: summary });
      if (size <= 10_000) await page.screenshot({ path: join(shotsDir, `perf-${size}.png`) });
      expect(marks["explorer:rendered"]).toBeGreaterThan(0);
    });
  }
});
