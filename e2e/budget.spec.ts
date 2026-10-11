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

  // Both e2e backends run with REFRESH_DISABLED=1 (scripts/start_backend.sh): no real network from e2e.
  test("shows EmptyState; refresh is disabled in this instance with a Polish message", async ({ page, request }) => {
    await page.goto("/");
    await expect(page.getByText("DANE SYNTETYCZNE – nie są to dane GUS/MF")).toHaveCount(0);
    const empty = page.locator(".empty-state");
    await expect(empty).toContainText("Brak danych źródłowych");
    await expect(empty.getByRole("alert")).toContainText("Odświeżanie wyłączone w tej instancji");
    await expect(empty.getByRole("button", { name: "Odśwież dane" })).toBeDisabled();
    await expect(empty).not.toContainText("Odświeżenie nie powiodło się");

    // the API itself refuses to start a job
    const post = await request.post("/api/refresh");
    expect(post.status()).toBe(403);
    expect(await post.json()).toEqual({ detail: "odświeżanie wyłączone w tej instancji" });
    const status = await (await request.get("/api/refresh/status")).json();
    expect(status.disabled).toBe(true);
    expect(status.state).toBe("idle");
  });
});

test.describe("seeded store (synthetic data)", () => {
  test.use({ colorScheme: "light" });

  test("synthetic data is labelled with a persistent banner", async ({ page }) => {
    await page.goto("/");
    const banner = page.getByRole("status").filter({ hasText: "DANE SYNTETYCZNE – nie są to dane GUS/MF" });
    await expect(banner).toBeVisible();
    await expect(banner.getByRole("button")).toHaveCount(0);
    // still there once the charts have loaded
    await expect(page.getByTestId("metric-row")).toContainText("mld zł");
    await expect(banner).toBeVisible();
  });

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

    // Regression: the provenance footer ("DANE SYNTETYCZNE …") must be legible, not clipped by the chart's own viewBox.
    // The seeded instance is synthetic, so a footer strip (22 CSS px, rendered at scale 2) is present at the bottom.
    const layout = await page.evaluate(async (b64) => {
      const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
      const bmp = await createImageBitmap(new Blob([bin], { type: "image/png" }));
      const c = document.createElement("canvas");
      c.width = bmp.width;
      c.height = bmp.height;
      const ctx = c.getContext("2d")!;
      ctx.drawImage(bmp, 0, 0);
      const { data, width, height } = ctx.getImageData(0, 0, c.width, c.height);
      const rowsAlpha = (from: number, to: number) => {
        let transparent = 0;
        for (let y = from; y < to; y++) for (let x = 0; x < width; x++) if (data[(y * width + x) * 4 + 3] < 255) transparent++;
        return transparent;
      };
      const bg = [data[(height - 1) * width * 4], data[(height - 1) * width * 4 + 1], data[(height - 1) * width * 4 + 2]];
      const footerTop = height - 22 * 2; // device pixels
      let ink = 0;
      let inkRows = new Set<number>();
      for (let y = footerTop; y < height; y++) {
        for (let x = 0; x < width; x++) {
          const i = (y * width + x) * 4;
          if (Math.abs(data[i] - bg[0]) + Math.abs(data[i + 1] - bg[1]) + Math.abs(data[i + 2] - bg[2]) > 90) {
            ink++;
            inkRows.add(y);
          }
        }
      }
      return { transparentTop: rowsAlpha(0, 24), transparentBottom: rowsAlpha(height - 24, height), ink, inkRowSpan: inkRows.size };
    }, pngBytes.toString("base64"));
    // No transparent bands (the clipped export had ~11 empty rows at the top and bottom).
    expect(layout.transparentTop).toBe(0);
    expect(layout.transparentBottom).toBe(0);
    // Footer text is fully drawn: many ink pixels spread over most of an 11px text line (≈ 8+ device rows), not just a 3–4 row sliver.
    expect(layout.ink).toBeGreaterThan(400);
    expect(layout.inkRowSpan).toBeGreaterThanOrEqual(8);

    const [pdf] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Wykresy PDF" }).click()]);
    const pdfBytes = await read(pdf);
    expect(pdfBytes.subarray(0, 4).toString("latin1")).toBe("%PDF");
    expect(pdfBytes.length).toBeGreaterThan(2000);
  });

  test("quality tab shows status badges and sources for model constants", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("metric-row")).toContainText("mld zł");
    await page.getByRole("tab", { name: "Jakość modelu" }).click();
    const table = page.getByRole("table", { name: /Stałe i założenia modelu/ });
    await expect(table.locator(".badge", { hasText: "założenie" }).first()).toBeVisible();
    await expect(table.locator(".badge", { hasText: "ze źródła" }).first()).toBeVisible();
    await expect(page.locator(".results")).not.toContainText("PLACEHOLDER");
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
