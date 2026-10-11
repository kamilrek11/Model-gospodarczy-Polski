import type { ChartPng } from "./chartImage";
import { pdfSafe } from "./provenance";

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(new Error("Nie udało się odczytać obrazu."));
    r.readAsDataURL(blob);
  });
}

/** PDF (A4, poziomo) z jednym wykresem na stronę; jspdf ładowany leniwie. `notes` (pochodzenie danych) na każdej stronie, w ASCII. */
export async function chartsToPdf(charts: ChartPng[], title: string, notes: string[] = []): Promise<Blob> {
  const { jsPDF } = await import("jspdf");
  const doc = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" });
  const pageW = doc.internal.pageSize.getWidth();
  const pageH = doc.internal.pageSize.getHeight();
  const margin = 12;
  let first = true;
  for (const c of charts) {
    if (!first) doc.addPage();
    first = false;
    doc.setFontSize(12);
    doc.text(pdfSafe(title), margin, margin);
    doc.setFontSize(9);
    notes.forEach((n, i) => doc.text(pdfSafe(n), margin, margin + 5 + i * 4));
    const top = margin + 6 + notes.length * 4;
    const scale = Math.min((pageW - 2 * margin) / c.width, (pageH - margin - top) / c.height);
    doc.addImage(await blobToDataUrl(c.blob), "PNG", margin, top, c.width * scale, c.height * scale);
  }
  return doc.output("blob");
}
