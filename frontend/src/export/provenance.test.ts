import { describe, expect, it, vi } from "vitest";
import { sim } from "../testFixtures";
import { prepareSvg } from "./chartImage";
import { pdfSafe, provenanceLines } from "./provenance";

const getVar = (n: string) => ({ "--surface-1": "#ffffff", "--text-secondary": "#52514e" })[n] ?? "";

function svg() {
  const host = document.createElement("div");
  host.innerHTML = '<svg width="400" height="300"><path d="M0 0"/></svg>';
  return host.firstElementChild as SVGSVGElement;
}

describe("provenance of image/PDF exports", () => {
  it("lists data date and model version; adds DANE SYNTETYCZNE only when flagged", () => {
    expect(provenanceLines({ ...sim, synthetic: false })).toEqual(["Dane z: 09.10.2026 · model test"]);
    const lines = provenanceLines({ ...sim, synthetic: true, model_version: "abcdef123456" });
    expect(lines).toEqual(["Dane z: 09.10.2026 · model abcdef1", "DANE SYNTETYCZNE – nie są to dane GUS/MF"]);
    expect(provenanceLines({ ...sim, data_updated_at: null, model_version: undefined })).toEqual(["Dane z: brak"]);
  });

  it("pdfSafe produces ASCII for the default PDF font", () => {
    expect(pdfSafe("DANE SYNTETYCZNE – nie są to dane GUS/MF · Łódź żółć")).toBe("DANE SYNTETYCZNE - nie sa to dane GUS/MF - Lodz zolc");
    expect(pdfSafe("Dane z: 09.10.2026 · model x")).toMatch(/^[\x20-\x7e]*$/);
  });

  it("prepareSvg adds a visible footer line below the chart", () => {
    const { markup, height, width } = prepareSvg(svg(), getVar, "Dane z: 09.10.2026 · DANE SYNTETYCZNE – nie są to dane GUS/MF");
    expect(width).toBe(400);
    expect(height).toBeGreaterThan(300);
    expect(markup).toMatch(/<text[^>]*>Dane z: 09\.10\.2026 · DANE SYNTETYCZNE – nie są to dane GUS\/MF<\/text>/);
    expect(markup).toMatch(/height="(3[1-9]\d)"/);
  });

  it("prepareSvg without footer keeps the original size", () => {
    expect(prepareSvg(svg(), getVar).height).toBe(300);
  });

  it("chartsToPdf writes the provenance lines on every page", async () => {
    const texts: string[] = [];
    vi.doMock("jspdf", () => ({
      jsPDF: class {
        internal = { pageSize: { getWidth: () => 297, getHeight: () => 210 } };
        setFontSize() {}
        setTextColor() {}
        text(t: string) {
          texts.push(t);
        }
        addImage() {}
        addPage() {}
        output() {
          return new Blob(["%PDF"]);
        }
      },
    }));
    const { chartsToPdf } = await import("./pdf");
    const png = { blob: new Blob(["x"], { type: "image/png" }), width: 400, height: 300 };
    await chartsToPdf([png, png], "Tytul", ["Dane z: 09.10.2026", "DANE SYNTETYCZNE – nie są to dane GUS/MF"]);
    expect(texts.filter((t) => t === "DANE SYNTETYCZNE - nie sa to dane GUS/MF")).toHaveLength(2);
    expect(texts.filter((t) => t === "Dane z: 09.10.2026")).toHaveLength(2);
    vi.doUnmock("jspdf");
  });
});
