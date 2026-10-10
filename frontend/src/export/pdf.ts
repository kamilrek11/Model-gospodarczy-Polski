import type { ChartPng } from "./chartImage";

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(new Error("Nie udało się odczytać obrazu."));
    r.readAsDataURL(blob);
  });
}

/** PDF (A4, poziomo) z jednym wykresem na stronę; jspdf ładowany leniwie. */
export async function chartsToPdf(charts: ChartPng[], title: string): Promise<Blob> {
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
    doc.text(title, margin, margin);
    const scale = Math.min((pageW - 2 * margin) / c.width, (pageH - 2 * margin - 6) / c.height);
    doc.addImage(await blobToDataUrl(c.blob), "PNG", margin, margin + 6, c.width * scale, c.height * scale);
  }
  return doc.output("blob");
}
