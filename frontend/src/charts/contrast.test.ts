import css from "../styles.css?raw";

/** WCAG 2.x: względna luminancja i współczynnik kontrastu. */
function luminance(hex: string): number {
  const v = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(v.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** Tokeny z pierwszego bloku zaczynającego się od `selector {` w styles.css. */
function tokens(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  expect(start, selector).toBeGreaterThanOrEqual(0);
  const body = css.slice(start, css.indexOf("}", start));
  return Object.fromEntries([...body.matchAll(/(--[\w-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1], m[2].toLowerCase()]));
}

describe("series colours vs chart surface (WCAG non-text contrast >= 3:1)", () => {
  it("helper matches known WCAG values", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrast("#1baf7a", "#fcfcfb")).toBeLessThan(3); // the old light aqua (~2.6:1)
  });

  for (const [name, selector] of [
    ["light", ":root"],
    ["dark (toggle)", ':root[data-theme="dark"]'],
  ] as const) {
    it(`${name}: series 1-3 reach 3:1 and stay distinct`, () => {
      const t = tokens(selector);
      const series = ["--series-1", "--series-2", "--series-3"].map((k) => t[k]);
      for (const c of series) expect(contrast(c, t["--surface-1"]), c).toBeGreaterThanOrEqual(3);
      expect(new Set(series).size).toBe(3);
    });
  }
});
