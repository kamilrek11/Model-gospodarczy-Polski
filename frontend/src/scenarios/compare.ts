import type { Band, SimulationResult, TaxKey } from "../api/types";
import { TAX_ORDER } from "../charts/palette";

export type Comparable = Pick<SimulationResult, "years"> & { taxes: Partial<Record<TaxKey, Pick<Band, "median">>> };

export interface DiffRow {
  tax: TaxKey;
  year: number;
  /** Mediana w mld zł; null gdy brak podatku/roku w danym wyniku. */
  a: number | null;
  b: number | null;
  /** b - a (mld zł); null gdy brakuje którejś strony. */
  diff: number | null;
  /** (b - a) / |a| w %; null gdy brak danych lub a = 0. */
  pct: number | null;
}

function medianAt(r: Comparable, tax: TaxKey, year: number): number | null {
  const i = r.years.indexOf(year);
  const v = i < 0 ? undefined : r.taxes[tax]?.median?.[i];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** Różnice median per podatek i rok; wiersze dla sumy lat obu wyników, bez NaN. */
export function compare(a: Comparable, b: Comparable): DiffRow[] {
  const years = [...new Set([...a.years, ...b.years])].sort((x, y) => x - y);
  const rows: DiffRow[] = [];
  for (const tax of TAX_ORDER) {
    if (!a.taxes[tax] && !b.taxes[tax]) continue;
    for (const year of years) {
      const av = medianAt(a, tax, year);
      const bv = medianAt(b, tax, year);
      if (av === null && bv === null) continue;
      const diff = av !== null && bv !== null ? bv - av : null;
      const pct = diff !== null && av !== null && av !== 0 ? (diff / Math.abs(av)) * 100 : null;
      rows.push({ tax, year, a: av, b: bv, diff, pct });
    }
  }
  return rows;
}
