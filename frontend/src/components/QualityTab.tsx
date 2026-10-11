import { useEffect, useState } from "react";
import { ApiError, getBacktest } from "../api/client";
import type { AssumptionValue, BacktestResult, SimulationResult, TaxKey } from "../api/types";
import { TAX_LABEL, TAX_ORDER } from "../charts/palette";

const pctFmt = new Intl.NumberFormat("pl-PL", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const numFmt = new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 4 });

export const isPlaceholder = (status: string): boolean => status === "assumption";

const STATUS_LABEL: Record<string, string> = {
  from_data: "z danych",
  sourced: "ze źródła",
  assumption: "założenie",
  "model-structure": "struktura modelu",
  calibrated: "kalibracja",
};
export const statusLabel = (status: string): string => STATUS_LABEL[status] ?? status;

/** Tylko http(s): adres ze źródła zewnętrznego nie może być linkiem javascript: ani data:. */
const isHttpUrl = (u: string | undefined): u is string => {
  if (!u) return false;
  try {
    const p = new URL(u).protocol;
    return p === "http:" || p === "https:";
  } catch {
    return false;
  }
};

const rangeText = (low: number | null | undefined, high: number | null | undefined): string =>
  typeof low === "number" && typeof high === "number" ? `${numFmt.format(low)}–${numFmt.format(high)}` : "–";

const fmtValue = (v: unknown): string => (typeof v === "number" && Number.isFinite(v) ? numFmt.format(v) : "–");

/** Polska odmiana liczebnika: 1 grupa, 2-4 grupy, 5+ grup. */
function plural(n: number, one: string, few: string, many: string): string {
  if (n === 1) return one;
  const d = n % 10;
  const t = n % 100;
  return d >= 2 && d <= 4 && (t < 12 || t > 14) ? few : many;
}

/** Wartość założenia: liczba, słownik (klucz: wartość) albo macierz (podsumowanie + tabela w <details>). */
export function AssumptionValueView({ value, label }: { value: AssumptionValue; label: string }) {
  if (value === null || value === undefined) return null;
  if (typeof value === "number") return <> = {fmtValue(value)}</>;
  if (Array.isArray(value)) {
    const cols = Math.max(0, ...value.map((r) => (Array.isArray(r) ? r.length : 0)));
    return (
      <>
        {" "}
        = {value.length} {plural(value.length, "grupa", "grupy", "grup")} × {cols} {plural(cols, "kolumna", "kolumny", "kolumn")}
        <details className="assumption-data">
          <summary>Pokaż dane</summary>
          <div className="table-scroll">
            <table className="data-table">
              <caption>{label}</caption>
              <tbody>
                {value.map((row, i) => (
                  <tr key={i}>
                    {(Array.isArray(row) ? row : [row]).map((c, j) => (
                      <td key={j}>{fmtValue(c)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </>
    );
  }
  if (typeof value === "object") {
    return (
      <ul className="kv-list">
        {Object.entries(value).map(([k, v]) => (
          <li key={k}>
            {k}: {fmtValue(v)}
          </li>
        ))}
      </ul>
    );
  }
  return <> = {String(value)}</>;
}

export function QualityTab({ sim, refreshKey = 0 }: { sim: SimulationResult | null; refreshKey?: number }) {
  const [bt, setBt] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const c = new AbortController();
    setError(null);
    getBacktest(c.signal)
      .then(setBt)
      .catch((e: unknown) => {
        if (c.signal.aborted) return;
        setBt(null);
        setError(e instanceof ApiError ? e.message : "Nie udało się pobrać wyników backtestu");
      });
    return () => c.abort();
  }, [refreshKey]);

  const taxes = TAX_ORDER.filter((t) => bt && (bt.mape[t] !== undefined || bt.coverage80[t] !== undefined || bt.coverage95[t] !== undefined));
  const cell = (v: number | undefined, f: (n: number) => string) => (v === undefined || !Number.isFinite(v) ? "–" : f(v));
  const placeholders = sim?.assumptions.filter((a) => isPlaceholder(a.status)) ?? [];

  return (
    <div className="results">
      <section className="viz-card" aria-labelledby="bt-title">
        <h2 id="bt-title">Backtest modelu</h2>
        {error && <p role="alert">{error}</p>}
        {!bt && !error && <p className="note">Ładowanie wyników backtestu…</p>}
        {bt && (
          <>
            {bt.message && <p className="note">{bt.message}</p>}
            {taxes.length > 0 && (
              <div className="table-scroll">
                <table className="data-table">
                  <caption>
                    Dokładność prognoz historycznych (początki prognoz: {bt.n_origins}, pominięte: {bt.n_skipped})
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Podatek</th>
                      <th scope="col">MAPE</th>
                      <th scope="col">Pokrycie 80%</th>
                      <th scope="col">Pokrycie 95%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {taxes.map((t: TaxKey) => (
                      <tr key={t}>
                        <th scope="row">{TAX_LABEL[t]}</th>
                        <td>{cell(bt.mape[t], (n) => `${pctFmt.format(n)}%`)}</td>
                        <td>{cell(bt.coverage80[t], (n) => `${pctFmt.format(n * 100)}%`)}</td>
                        <td>{cell(bt.coverage95[t], (n) => `${pctFmt.format(n * 100)}%`)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="note">
              Liczba początków prognoz: {bt.n_origins}; pominięte: {bt.n_skipped}.
            </p>
            {bt.notes.length > 0 && (
              <ul className="note-list">
                {bt.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            )}
          </>
        )}
      </section>

      <section className="viz-card" aria-labelledby="as-title">
        <h2 id="as-title">Założenia modelu</h2>
        {!sim ? (
          <p className="note">Brak bieżącej symulacji – założenia pojawią się po jej obliczeniu.</p>
        ) : (
          <>
            {placeholders.length > 0 && (
              <p className="notice warn" role="note">
                {placeholders.length} z założeń nie ma źródła (status „założenie”) – to wartości orientacyjne. Wyniki zależą od nich, więc traktuj je ostrożnie.
              </p>
            )}
            <div className="table-scroll">
              <table className="data-table assumptions-table">
                <caption>Stałe i założenia modelu: status, źródło i zakres niepewności</caption>
                <thead>
                  <tr>
                    <th scope="col">Stała</th>
                    <th scope="col">Wartość</th>
                    <th scope="col">Status</th>
                    <th scope="col">Źródło</th>
                    <th scope="col">Zakres</th>
                    <th scope="col">Uwagi</th>
                  </tr>
                </thead>
                <tbody>
                  {sim.assumptions.map((a) => {
                    const src = a.source ? `${a.source}${a.year ? ` (${a.year})` : ""}` : a.year ? `${a.year}` : "–";
                    return (
                      <tr key={a.key} className={isPlaceholder(a.status) ? "assumption placeholder" : "assumption"}>
                        <th scope="row">
                          <code>{a.key}</code>
                        </th>
                        <td>
                          <AssumptionValueView value={a.value} label={a.key} />
                        </td>
                        <td>
                          <span className={isPlaceholder(a.status) ? "badge badge-warn" : "badge"}>{statusLabel(a.status)}</span>
                        </td>
                        <td>
                          {isHttpUrl(a.url) ? (
                            <a href={a.url} target="_blank" rel="noopener noreferrer">
                              {src === "–" ? a.url : src}
                            </a>
                          ) : (
                            src
                          )}
                        </td>
                        <td>{rangeText(a.low, a.high)}</td>
                        <td>
                          <small>{a.note}</small>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <h3>Współczynniki kalibracji</h3>
            {Object.keys(sim.calibration).length === 0 ? (
              <p className="note">Brak kalibracji.</p>
            ) : (
              <div className="table-scroll">
                <table className="data-table">
                  <caption>Współczynniki kalibracji względem historii</caption>
                  <thead>
                    <tr>
                      <th scope="col">Podatek</th>
                      <th scope="col">Współczynnik</th>
                      <th scope="col">Lata</th>
                      <th scope="col">Metoda</th>
                    </tr>
                  </thead>
                  <tbody>
                    {TAX_ORDER.filter((t) => sim.calibration[t]).map((t) => {
                      const c = sim.calibration[t]!;
                      return (
                        <tr key={t}>
                          <th scope="row">{TAX_LABEL[t]}</th>
                          <td>{numFmt.format(c.factor)}</td>
                          <td>{c.years.length ? `${c.years[0]}–${c.years[c.years.length - 1]}` : "–"}</td>
                          <td>{c.method}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
