import { describe, expect, it, vi } from "vitest";
import { chartToPng, prepareSvg, resolveCssVars, svgSize } from "./chartImage";

const vars: Record<string, string> = { "--series-1": "#2a78d6", "--surface-1": "#1a1a19", "--text-primary": "#f0efec" };
const getVar = (n: string) => vars[n] ?? "";

function makeSvg(attrs = 'width="400" height="300"') {
  const host = document.createElement("div");
  host.innerHTML = `<svg ${attrs} class="recharts-surface"><path stroke="var(--series-1)" fill="var(--missing, #123456)"/><text style="fill: var(--text-primary)">x</text></svg>`;
  return host.firstElementChild as SVGSVGElement;
}

describe("chart image helpers", () => {
  it("resolveCssVars substitutes values and fallbacks", () => {
    expect(resolveCssVars('stroke="var(--series-1)"', getVar)).toBe('stroke="#2a78d6"');
    expect(resolveCssVars("fill: var( --missing , #123456 )", getVar)).toBe("fill: #123456");
    expect(resolveCssVars("var(--missing)", getVar)).toBe("#000000");
  });

  it("svgSize prefers attributes and falls back to defaults", () => {
    expect(svgSize(makeSvg())).toEqual({ width: 400, height: 300 });
    expect(svgSize(makeSvg('viewBox="0 0 500 250"'))).toEqual({ width: 500, height: 250 });
    expect(svgSize(makeSvg(""))).toEqual({ width: 600, height: 340 });
  });

  it("prepareSvg leaves no CSS variables, adds namespace and a background rect", () => {
    const { markup, width, height } = prepareSvg(makeSvg(), getVar);
    expect(markup).not.toContain("var(");
    expect(markup).toContain("#2a78d6");
    expect(markup).toContain('xmlns="http://www.w3.org/2000/svg"');
    expect(markup).toMatch(/<rect[^>]*fill="#1a1a19"/);
    expect(markup.indexOf("<rect")).toBeLessThan(markup.indexOf("<path"));
    expect([width, height]).toEqual([400, 300]);
  });

  it("chartToPng passes resolved markup to the (stubbed) rasteriser", async () => {
    const blob = new Blob(["png"], { type: "image/png" });
    const rasterize = vi.fn(async () => blob);
    const r = await chartToPng(makeSvg(), rasterize, getVar);
    expect(rasterize).toHaveBeenCalledOnce();
    const [markup, w, h] = rasterize.mock.calls[0] as unknown as [string, number, number];
    expect(markup).not.toContain("var(");
    expect([w, h]).toEqual([400, 300]);
    expect(r).toEqual({ blob, width: 400, height: 300 });
  });
});
