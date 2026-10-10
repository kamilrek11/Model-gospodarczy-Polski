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

  it("footer fits inside the canvas for a Recharts-style SVG that carries a viewBox", () => {
    const footer = "DANE SYNTETYCZNE – nie są to dane GUS/MF";
    const { markup, width, height } = prepareSvg(makeSvg('width="400" height="300" viewBox="0 0 400 300"'), getVar, footer);
    expect([width, height]).toEqual([400, 322]);

    const doc = new DOMParser().parseFromString(markup, "image/svg+xml");
    const outer = doc.documentElement;
    // The outer canvas viewBox must match the exported pixel size, otherwise the content is shifted/clipped.
    expect(outer.getAttribute("viewBox")).toBe("0 0 400 322");
    expect(outer.getAttribute("width")).toBe("400");
    expect(outer.getAttribute("height")).toBe("322");

    // The original chart keeps its own size and viewBox and sits at the top-left corner (no centring offset).
    const chart = outer.querySelector("svg")!;
    expect(chart.getAttribute("viewBox")).toBe("0 0 400 300");
    expect(chart.getAttribute("width")).toBe("400");
    expect(chart.getAttribute("height")).toBe("300");
    expect(chart.getAttribute("x")).toBe("0");
    expect(chart.getAttribute("y")).toBe("0");

    // The footer belongs to the outer canvas and its baseline lies in the added strip, inside the canvas.
    const text = Array.from(outer.querySelectorAll("text")).find((t) => t.textContent === footer)!;
    expect(text.parentNode).toBe(outer);
    const y = Number(text.getAttribute("y"));
    expect(y).toBeGreaterThan(300);
    expect(y).toBeLessThan(322);

    // The background covers the whole canvas, footer strip included.
    const bg = outer.querySelector(":scope > rect")!;
    expect(bg.getAttribute("width")).toBe("100%");
    expect(bg.getAttribute("height")).toBe("100%");
  });

  it("without a footer the canvas is exactly the chart size and the chart is still wrapped consistently", () => {
    const { markup, width, height } = prepareSvg(makeSvg('width="400" height="300" viewBox="0 0 400 300"'), getVar);
    expect([width, height]).toEqual([400, 300]);
    const outer = new DOMParser().parseFromString(markup, "image/svg+xml").documentElement;
    expect(outer.getAttribute("viewBox")).toBe("0 0 400 300");
    expect(outer.querySelector("svg")!.getAttribute("height")).toBe("300");
    expect(outer.querySelector("text[font-size='11']")).toBeNull();
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
