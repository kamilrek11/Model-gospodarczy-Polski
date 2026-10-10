const LOCALE = "pl-PL";

const mld = new Intl.NumberFormat(LOCALE, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const mldSigned = new Intl.NumberFormat(LOCALE, { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: "exceptZero" });
const pct = new Intl.NumberFormat(LOCALE, { minimumFractionDigits: 1, maximumFractionDigits: 1, signDisplay: "exceptZero" });
const axis = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });

/** Kwota w mld zł, dwa miejsca po przecinku (bez jednostki). */
export const fmtMld = (v: number): string => mld.format(v);
/** Jak fmtMld, ze znakiem + / - (zero bez znaku). */
export const fmtSignedMld = (v: number): string => mldSigned.format(v);
/** Procent ze znakiem, jedno miejsce po przecinku; `v` w punktach procentowych. */
export const fmtPct = (v: number): string => `${pct.format(v)}%`;
export const fmtAxis = (v: number): string => axis.format(v);

/** ISO -> dd.mm.rrrr (strefa Europe/Warsaw). */
export function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat(LOCALE, { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "Europe/Warsaw" }).format(d);
}
