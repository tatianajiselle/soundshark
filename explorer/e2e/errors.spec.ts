import { expect, fakeMap, test } from "./fixtures";

const sample = () => structuredClone(fakeMap());

test.describe("a missing or broken map", () => {
  test("says so when map.json is missing", async ({ page }) => {
    await page.route("**/map.json", (route) => route.fulfill({ status: 404, body: "not here" }));
    await page.goto("/");
    const error = page.getByTestId("error");
    await expect(error).toContainText("There is no map here yet.");
    await expect(error).toContainText("map.json was not found");
    await expect(page.locator("html")).toHaveAttribute("data-status", "error");
  });

  test("says so when map.json is not JSON", async ({ page }) => {
    await page.route("**/map.json", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "{ not json" }),
    );
    await page.goto("/");
    await expect(page.getByTestId("error")).toContainText("map.json is not valid JSON");
  });

  test("names the problem when the file breaks the contract", async ({ page }) => {
    const wrong = { ...sample(), version: 2 };
    await page.route("**/map.json", (route) => route.fulfill({ status: 200, json: wrong }));
    await page.goto("/");
    await expect(page.getByTestId("error")).toContainText("The map file is not in the expected format.");
    await expect(page.getByTestId("error")).toContainText("unsupported map version 2");

    const broken = sample();
    broken.related[5] = [broken.related[5][0], 123456789, 0.1];
    await page.unroute("**/map.json");
    await page.route("**/map.json", (route) => route.fulfill({ status: 200, json: broken }));
    await page.reload();
    await expect(page.getByTestId("error")).toContainText("related[5] points at unknown artist 123456789");
  });

  test("says so when the server fails", async ({ page }) => {
    await page.route("**/map.json", (route) => route.fulfill({ status: 503, body: "busy" }));
    await page.goto("/");
    await expect(page.getByTestId("error")).toContainText("HTTP 503");
  });
});

test.describe("text from the file", () => {
  test("is shown as text and unsafe links are dropped", async ({ page }) => {
    const hostile = sample();
    hostile.artists[0].name = `<img src=x onerror="document.title='owned'">Zed`;
    hostile.artists[0].nights = 9999;
    hostile.credits = [
      { name: "Safe Source", url: "https://example.org/" },
      { name: "Sneaky Source", url: "javascript:alert(1)" },
    ];
    await page.route("**/map.json", (route) => route.fulfill({ status: 200, json: hostile }));
    let dialogs = 0;
    page.on("dialog", (dialog) => {
      dialogs += 1;
      void dialog.dismiss();
    });
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("data-status", "ready");

    const footer = page.getByTestId("footer");
    await expect(footer.getByRole("link", { name: "Safe Source" })).toHaveAttribute("href", "https://example.org/");
    await expect(footer).toContainText("Sneaky Source");
    await expect(footer.getByRole("link", { name: "Sneaky Source" })).toHaveCount(0);

    const input = page.getByRole("combobox", { name: "Search artists" });
    await input.fill("img src");
    await expect(page.getByRole("option").first()).toContainText(`<img src=x onerror="document.title='owned'">Zed`);
    await input.press("Enter");
    await expect(page.getByTestId("panel").getByRole("heading", { level: 2 })).toHaveText(
      `<img src=x onerror="document.title='owned'">Zed`,
    );
    await page.waitForTimeout(1500);
    await expect(page.locator(".map img")).toHaveCount(0);
    expect(await page.title()).not.toBe("owned");
    expect(dialogs).toBe(0);
  });
});
