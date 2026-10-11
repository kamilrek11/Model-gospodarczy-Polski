import type { SimulationResult } from "../api/types";
import { SYNTHETIC_TEXT } from "../components/SyntheticBanner";
import { fmtDate } from "../format";

/** Pochodzenie danych dla eksportu graficznego: data danych, wersja modelu, znacznik danych syntetycznych. */
export function provenanceLines(result: Pick<SimulationResult, "data_updated_at" | "model_version" | "synthetic">): string[] {
  const date = result.data_updated_at ? fmtDate(result.data_updated_at) : "brak";
  const first = `Dane z: ${date}${result.model_version ? ` · model ${result.model_version.slice(0, 7)}` : ""}`;
  return result.synthetic ? [first, SYNTHETIC_TEXT] : [first];
}

const ASCII_MAP: Record<string, string> = { ł: "l", Ł: "L", "–": "-", "—": "-", "·": "-", "×": "x" };

/** Domyślna czcionka jsPDF nie ma polskich znaków – zamiana na ASCII (ą->a, ł->l, – -> -). */
export function pdfSafe(text: string): string {
  return text
    .replace(/[łŁ–—·×]/g, (c) => ASCII_MAP[c])
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^\x20-\x7e]/g, "?");
}
