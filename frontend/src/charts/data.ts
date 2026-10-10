import type { HistoryData, SimulationResult, TaxKey } from "../api/types";
import { TAX_ORDER } from "./palette";

export interface ForecastRow {
  year: number;
  forecast: boolean;
  actual?: number;
  median?: number;
  band80?: [number, number];
  band95?: [number, number];
}

/**
 * Wiersze: lata historii (wykonanie) + lata prognozy (mediana i pasma 80% / 95%).
 * Polityka nakładania: JEDEN wiersz na rok. Jeśli rok jest i w historii, i w prognozie,
 * wiersz ma jednocześnie `actual` i `median` (linie łączą się wizualnie). Lata bez
 * żadnej wartości (luka między historią a prognozą) nie dostają wiersza – nic nie jest
 * zmyślane ani interpolowane.
 */
export function buildForecastSeries(history: HistoryData, sim: SimulationResult, tax: TaxKey): ForecastRow[] {
  const byYear = new Map<number, ForecastRow>();
  for (const p of history[tax] ?? []) byYear.set(p.year, { year: p.year, forecast: false, actual: p.value });
  const band = sim.taxes[tax];
  if (band) {
    sim.years.forEach((year, i) => {
      const row = byYear.get(year) ?? { year, forecast: true };
      row.forecast = true;
      row.median = band.median[i];
      row.band80 = [band.p10[i], band.p90[i]];
      row.band95 = [band.p2_5[i], band.p97_5[i]];
      byYear.set(year, row);
    });
  }
  return [...byYear.values()].sort((a, b) => a.year - b.year);
}

/** Dla wykresu: ostatni rok wykonania łączy się z prognozą (pasma o zerowej szerokości). */
export function bridgeForecast(rows: ForecastRow[]): ForecastRow[] {
  const firstF = rows.findIndex((r) => r.forecast);
  if (firstF <= 0 || rows[firstF].actual !== undefined) return rows;
  let i = firstF - 1;
  while (i >= 0 && rows[i].actual === undefined) i--;
  if (i < 0) return rows;
  const prev = rows[i];
  const v = prev.actual as number;
  const out = rows.slice();
  out[i] = { ...prev, median: v, band80: [v, v], band95: [v, v] };
  return out;
}

export interface Change {
  firstYear: number;
  lastYear: number;
  lastDelta: number;
  lastPct: number | null;
  totalDelta: number;
  totalPct: number | null;
}

/** Zmiana scenariusza względem bazy (mediana): ostatni rok prognozy i suma za horyzont. */
export function changeVsBaseline(sim: SimulationResult, tax: TaxKey): Change | null {
  const band = sim.taxes[tax];
  const base = sim.baseline[tax]?.median;
  if (!band || !base || band.median.length === 0 || base.length !== band.median.length) return null;
  const n = band.median.length;
  const lastDelta = band.median[n - 1] - base[n - 1];
  const sum = (a: number[]) => a.reduce((s, v) => s + v, 0);
  const totalDelta = sum(band.median) - sum(base);
  const pct = (d: number, b: number) => (b === 0 ? null : (d / b) * 100);
  return {
    firstYear: sim.years[0],
    lastYear: sim.years[n - 1],
    lastDelta,
    lastPct: pct(lastDelta, base[n - 1]),
    totalDelta,
    totalPct: pct(totalDelta, sum(base)),
  };
}

export type StackRow = { year: number; forecast: boolean } & Partial<Record<TaxKey, number>>;

/**
 * Słupki skumulowane. Polityka nakładania: wykonanie wygrywa – rok, w którym historia ma
 * dane dla któregokolwiek podatku, pokazuje wyłącznie wykonanie (forecast=false), a mediany
 * prognozy dla tego roku są pomijane (mediana nigdy nie jest podpisana jako wykonanie).
 * Pozostałe lata prognozy: mediana, forecast=true. Ukryte serie są pominięte.
 */
export function buildStackRows(history: HistoryData, sim: SimulationResult, hidden: ReadonlySet<TaxKey>): StackRow[] {
  const realisedYears = new Set<number>();
  for (const tax of TAX_ORDER) for (const p of history[tax] ?? []) realisedYears.add(p.year);

  const byYear = new Map<number, StackRow>();
  const row = (year: number) => {
    let r = byYear.get(year);
    if (!r) byYear.set(year, (r = { year, forecast: !realisedYears.has(year) }));
    return r;
  };
  for (const tax of TAX_ORDER) {
    if (hidden.has(tax)) continue;
    for (const p of history[tax] ?? []) row(p.year)[tax] = p.value;
    const band = sim.taxes[tax];
    if (band) sim.years.forEach((y, i) => realisedYears.has(y) || (row(y)[tax] = band.median[i]));
  }
  return [...byYear.values()].sort((a, b) => a.year - b.year);
}
