/** Eksport wykresu (SVG z Recharts) do PNG; czyste części są testowalne bez canvasu. */

const VAR_RE = /var\(\s*(--[\w-]+)\s*(?:,\s*([^)]+?))?\s*\)/g;

/** Podmienia var(--x[, fallback]) na konkretne wartości (SVG poza stroną nie widzi zmiennych CSS). */
export function resolveCssVars(svg: string, getVar: (name: string) => string): string {
  return svg.replace(VAR_RE, (_m, name: string, fallback?: string) => getVar(name).trim() || fallback?.trim() || "#000000");
}

export function svgSize(svg: Element): { width: number; height: number } {
  const num = (v: string | null) => {
    const n = v === null ? NaN : parseFloat(v);
    return Number.isFinite(n) && n > 0 ? n : NaN;
  };
  const rect = svg.getBoundingClientRect();
  const vb = svg.getAttribute("viewBox")?.split(/[\s,]+/).map(Number);
  const width = num(svg.getAttribute("width")) || rect.width || (vb && vb[2]) || 0;
  const height = num(svg.getAttribute("height")) || rect.height || (vb && vb[3]) || 0;
  return { width: Math.ceil(width) || 600, height: Math.ceil(height) || 340 };
}

export const FOOTER_HEIGHT = 22;

const SVG_NS = "http://www.w3.org/2000/svg";

/**
 * Samodzielny dokument SVG: bez zmiennych CSS, z tłem i rozmiarem; opcjonalna stopka (pochodzenie danych) pod wykresem.
 *
 * Wykres Recharts ma własny viewBox, więc samo podniesienie jego `height` o wysokość stopki przesuwa treść
 * (xMidYMid meet) i wypycha stopkę poza obraz. Dlatego oryginalny SVG zostaje zagnieżdżony w zewnętrznym płótnie
 * o rozmiarze eksportu (viewBox = rozmiar w pikselach): wykres zachowuje swój viewBox i leży w lewym górnym rogu,
 * a tło i stopka są rysowane we współrzędnych płótna.
 */
export function prepareSvg(svg: Element, getVar: (name: string) => string, footer?: string): { markup: string; width: number; height: number } {
  const { width, height: chartHeight } = svgSize(svg);
  const height = footer ? chartHeight + FOOTER_HEIGHT : chartHeight;
  const doc = svg.ownerDocument;

  const chart = svg.cloneNode(true) as Element;
  chart.removeAttribute("xmlns");
  chart.setAttribute("x", "0");
  chart.setAttribute("y", "0");
  chart.setAttribute("width", String(width));
  chart.setAttribute("height", String(chartHeight));

  // Przestrzeń nazw wystarczy nadać w createElementNS – serializator sam emituje xmlns (ręczny atrybut dałby duplikat = niepoprawny XML).
  const canvas = doc.createElementNS(SVG_NS, "svg");
  canvas.setAttribute("width", String(width));
  canvas.setAttribute("height", String(height));
  canvas.setAttribute("viewBox", `0 0 ${width} ${height}`);
  canvas.setAttribute("font-family", getVar("--font-family") || "system-ui, sans-serif");

  const rect = doc.createElementNS(SVG_NS, "rect");
  rect.setAttribute("width", "100%");
  rect.setAttribute("height", "100%");
  rect.setAttribute("fill", getVar("--surface-1").trim() || "#ffffff");
  canvas.appendChild(rect);
  canvas.appendChild(chart);

  if (footer) {
    const text = doc.createElementNS(SVG_NS, "text");
    text.setAttribute("x", "8");
    text.setAttribute("y", String(height - 7));
    text.setAttribute("font-size", "11");
    text.setAttribute("fill", getVar("--text-secondary").trim() || "#52514e");
    text.textContent = footer;
    canvas.appendChild(text);
  }
  const markup = resolveCssVars(new XMLSerializer().serializeToString(canvas), getVar);
  return { markup, width, height };
}

export const cssVarReader = (): ((name: string) => string) => {
  const style = getComputedStyle(document.documentElement);
  return (name) => style.getPropertyValue(name);
};

/** Jedyne miejsce używające canvasu/Image – w testach podmieniane. */
export function rasterizeSvg(markup: string, width: number, height: number, scale = 2): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(new Blob([markup], { type: "image/svg+xml;charset=utf-8" }));
    img.onload = () => {
      URL.revokeObjectURL(url);
      const canvas = document.createElement("canvas");
      canvas.width = width * scale;
      canvas.height = height * scale;
      const ctx = canvas.getContext("2d");
      if (!ctx) return reject(new Error("Przeglądarka nie obsługuje eksportu obrazu."));
      ctx.scale(scale, scale);
      ctx.drawImage(img, 0, 0, width, height);
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Nie udało się wygenerować obrazu."))), "image/png");
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Nie udało się wygenerować obrazu wykresu."));
    };
    img.src = url;
  });
}

export interface ChartPng {
  blob: Blob;
  width: number;
  height: number;
}

export async function chartToPng(svg: Element, rasterize: typeof rasterizeSvg = rasterizeSvg, getVar = cssVarReader(), footer?: string): Promise<ChartPng> {
  const { markup, width, height } = prepareSvg(svg, getVar, footer);
  return { blob: await rasterize(markup, width, height), width, height };
}
