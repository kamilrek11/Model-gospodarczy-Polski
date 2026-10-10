import { useState } from "react";
import { ApiError, exportData, type ExportFormat } from "../api/client";
import type { SimulationResult } from "../api/types";
import { chartToPng } from "../export/chartImage";
import { downloadBlob } from "../export/download";

interface Props {
  result: SimulationResult | null;
  params: Record<string, number>;
  /** Zwraca elementy SVG wykresów do eksportu graficznego. */
  getCharts: () => Element[];
}

const PDF_TITLE = "Symulator wplywow budzetowych";

export function ExportBar({ result, params, getCharts }: Props) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const disabled = !result || busy !== null;

  const run = async (key: string, job: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    try {
      await job();
    } catch (e) {
      setError(e instanceof ApiError || e instanceof Error ? e.message : "Eksport nie powiódł się");
    } finally {
      setBusy(null);
    }
  };

  const data = (format: ExportFormat) =>
    run(format, async () => {
      if (!result) return;
      const { blob, filename } = await exportData(format, { params, result });
      downloadBlob(blob, filename);
    });

  const charts = async () => {
    const svgs = getCharts();
    if (svgs.length === 0) throw new Error("Brak wykresu do wyeksportowania.");
    return Promise.all(svgs.map((s) => chartToPng(s)));
  };

  const png = () =>
    run("png", async () => {
      const [first] = await charts();
      downloadBlob(first.blob, "wykres.png");
    });

  const pdf = () =>
    run("pdf", async () => {
      const all = await charts();
      const { chartsToPdf } = await import("../export/pdf");
      downloadBlob(await chartsToPdf(all, PDF_TITLE), "wykresy.pdf");
    });

  return (
    <div className="export-bar" role="group" aria-label="Eksport">
      <button type="button" onClick={() => void data("csv")} disabled={disabled}>
        Eksport CSV
      </button>
      <button type="button" onClick={() => void data("xlsx")} disabled={disabled}>
        Eksport XLSX
      </button>
      <button type="button" onClick={() => void png()} disabled={disabled}>
        Wykres PNG
      </button>
      <button type="button" onClick={() => void pdf()} disabled={disabled}>
        Wykresy PDF
      </button>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </div>
  );
}
