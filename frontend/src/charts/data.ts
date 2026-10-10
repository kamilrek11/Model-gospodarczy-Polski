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

/** Wiersze: lata historii (wykonanie) + lata prognozy (mediana i pasma 80% / 95%). */
export function buildForecastSeries(history: HistoryData, sim: SimulationResult, tax: TaxKey): ForecastRow[] {
  const rows: ForecastRow[] = (history[tax] ?? []).map((p) => ({ year: p.year, forecast: false, actual: p.value }));
  const band = sim.taxes[tax];
  if (band) {
    sim.years.forEach((year, i) => {
      rows.push({
        year,
        forecast: true,
        median: band.median[i],
        band80: [band.p10[i], band.p90[i]],
        band95: [band.p2_5[i], band.p97_5[i]],
      });
    });
  }
  return rows.sort((a, b) => a.year - b.year);
}

/** Dla wykresu: ostatni rok historii łączy się z prognozą (pasma o zerowej szerokości). */
export function bridgeForecast(rows: ForecastRow[]): ForecastRow[] {
  const firstF = rows.findIndex((r) => r.forecast);
  if (firstF <= 0) return rows;
  const prev = rows[firstF - 1];
  if (prev.actual === undefined) return rows;
  const out = rows.slice();
  out[firstF - 1] = { ...prev, median: prev.actual, band80: [prev.actual, prev.actual], band95: [prev.actual, prev.actual] };
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

/** Słupki skumulowane: wykonanie w latach historii, mediana w latach prognozy; ukryte serie pominięte. */
export function buildStackRows(history: HistoryData, sim: SimulationResult, hidden: ReadonlySet<TaxKey>): StackRow[] {
  const byYear = new Map<number, StackRow>();
  const row = (year: number, forecast: boolean) => {
    let r = byYear.get(year);
    if (!r) byYear.set(year, (r = { year, forecast }));
    return r;
  };
  for (const tax of TAX_ORDER) {
    if (hidden.has(tax)) continue;
    for (const p of history[tax] ?? []) row(p.year, false)[tax] = p.value;
    const band = sim.taxes[tax];
    if (band) sim.years.forEach((y, i) => (row(y, true)[tax] = band.median[i]));
  }
  return [...byYear.values()].sort((a, b) => a.year - b.year);
}
