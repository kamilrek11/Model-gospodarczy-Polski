import { expect, test, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { EMPTY } from "./playwright.config";

// All data behind the seeded backend is SYNTHETIC (see backend/scripts/seed_fixtures.py).

const VAT_LABEL = "VAT - stawka podstawowa";

async function openVat(page: Page) {
  await page.goto("/");
  await page.getByRole("group", { name: "Wybór podatku" }).getByRole("button", { name: "VAT" }).click();
  await expect(page.getByTestId("metric-row")).toContainText("mld zł");
}

const metricText = (page: Page) => page.getByTestId("metric-row").innerText();
const chartMarkup = (page: Page) => page.locator(".results .chart-frame svg.recharts-surface").first().innerHTML();

async function setVat(page: Page, percent: string) {
  await page.getByLabel(VAT_LABEL, { exact: true }).fill(percent);
}

async function read(download: import("@playwright/test").Download): Promise<Buffer> {
  const path = await download.path();
  return readFile(path);
}

test.describe("empty store", () => {
  test.use({ baseURL: EMPTY });

  test("shows EmptyState with refresh button; refresh against unmapped sources fails clearly", async ({ page }) => {
    await page.goto("/");
    const empty = page.locator(".empty-state");
    await expect(empty).toContainText("Brak danych źródłowych");
    await empty.getByRole("button", { name: "Odśwież dane" }).click();
    await expect(empty.getByRole("alert")).toContainText("Odświeżenie nie powiodło się");
    await expect(empty).toContainText("Brak danych źródłowych");
  });
});

test.describe("seeded store (synthetic data)", () => {
  test.use({ colorScheme: "light" });

  test("changing VAT standard rate to 25% updates chart and change-vs-baseline metric", async ({ page }) => {
    await openVat(page);
    await expect.poll(() => metricText(page)).toContain("0,00 mld zł");
    const before = await metricText(page);
    const chartBefore = await chartMarkup(page);
    await setVat(page, "25");
    // within debounce (300 ms) + request: metric shows a positive change vs baseline
    await expect.poll(() => metricText(page), { timeout: 8_000 }).toMatch(/\+\d[\d\s ]*,\d\d mld zł/);
    const after = await metricText(page);
    expect(after).not.toBe(before);
    await expect.poll(() => chartMarkup(page)).not.toBe(chartBefore);
    await expect(page.getByTestId("deviation-vat_rate_standard")).toBeVisible();
  });

  test("save scenario, load it, compare two scenarios", async ({ page }) => {
    await page.goto("/");
    const pick = page.getByLabel("Zapisane scenariusze");
    const name = page.getByLabel("Nazwa scenariusza");
    await name.fill("Bazowy");
    await page.getByRole("button", { name: "Zapisz scenariusz" }).click();
    await setVat(page, "25");
    await name.fill("VAT 25");
    await page.getByRole("button", { name: "Zapisz scenariusz" }).click();
    await expect(page.locator(".scenario-bar").getByRole("status")).toContainText("VAT 25");

    await pick.selectOption({ label: "Bazowy" });
    await page.getByRole("button", { name: "Wczytaj" }).click();
    await expect(page.getByLabel(VAT_LABEL, { exact: true })).toHaveValue("23");
    await pick.selectOption({ label: "VAT 25" });
    await page.getByRole("button", { name: "Wczytaj" }).click();
    await expect(page.getByLabel(VAT_LABEL, { exact: true })).toHaveValue("25");

    await page.getByRole("tab", { name: "Porównanie scenariuszy" }).click();
    await page.getByLabel("Scenariusz A").selectOption({ label: "Bazowy" });
    await page.getByLabel("Scenariusz B").selectOption({ label: "VAT 25" });
    await page.getByRole("button", { name: "Porównaj" }).click();
    const table = page.getByTestId("diff-table");
    await expect(table).toBeVisible();
    expect(await table.locator("tbody tr").count()).toBeGreaterThan(0);
    // VAT rows must show a positive difference (B - A)
    const vatRow = table.locator("tbody tr", { has: page.locator('th:text-is("VAT")') }).first();
    await expect(vatRow).toContainText(/\+\d/);
  });

  test("theme toggle changes data-theme and the computed body background", async ({ page }) => {
    await page.goto("/");
    const bg = () => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    await page.getByRole("button", { name: "Jasny" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    const light = await bg();
    await page.getByRole("button", { name: "Ciemny" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    const dark = await bg();
    expect(dark).not.toBe(light);
    expect(light).not.toBe("rgba(0, 0, 0, 0)");
  });

  test("PNG export is a real, non-blank PNG; PDF export is a PDF", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Wykres PNG" })).toBeEnabled();

    const [png] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Wykres PNG" }).click()]);
    const pngBytes = await read(png);
    expect([...pngBytes.subarray(0, 8)]).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
    // not blank: decode in the browser and count distinct colours
    const colours = await page.evaluate(async (b64) => {
      const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
      const bmp = await createImageBitmap(new Blob([bin], { type: "image/png" }));
      const c = document.createElement("canvas");
      c.width = bmp.width;
      c.height = bmp.height;
      const ctx = c.getContext("2d")!;
      ctx.drawImage(bmp, 0, 0);
      const d = ctx.getImageData(0, 0, c.width, c.height).data;
      const set = new Set<number>();
      for (let i = 0; i < d.length; i += 4) set.add((d[i] << 16) | (d[i + 1] << 8) | d[i + 2]);
      return { n: set.size, w: bmp.width, h: bmp.height };
    }, pngBytes.toString("base64"));
    expect(colours.w).toBeGreaterThan(100);
    expect(colours.n).toBeGreaterThan(5);

    const [pdf] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Wykresy PDF" }).click()]);
    const pdfBytes = await read(pdf);
    expect(pdfBytes.subarray(0, 4).toString("latin1")).toBe("%PDF");
    expect(pdfBytes.length).toBeGreaterThan(2000);
  });

  test("importing a scenario with an out-of-range value is rejected in Polish", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByLabel(VAT_LABEL, { exact: true })).toBeVisible();
    const file = JSON.stringify({ version: 1, scenarios: [{ name: "Zly", params: { vat_rate_standard: 1e308 }, savedAt: "2026-10-10T00:00:00Z" }] });
    await page.getByLabel("Plik scenariuszy (JSON)").setInputFiles({ name: "zly.json", mimeType: "application/json", buffer: Buffer.from(file) });
    await expect(page.locator(".scenario-bar").getByRole("alert")).toContainText("poza dozwolonym zakresem");
    await expect(page.getByLabel("Zapisane scenariusze").locator("option", { hasText: "Zly" })).toHaveCount(0);
  });
});
