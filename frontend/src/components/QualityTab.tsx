import { useEffect, useState } from "react";
import { ApiError, getBacktest } from "../api/client";
import type { BacktestResult, SimulationResult, TaxKey } from "../api/types";
import { TAX_LABEL, TAX_ORDER } from "../charts/palette";

const pctFmt = new Intl.NumberFormat("pl-PL", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const numFmt = new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 4 });

export const isPlaceholder = (status: string): boolean => status.includes("PLACEHOLDER");

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
                {placeholders.length} z założeń to wartości orientacyjne, niezweryfikowane (PLACEHOLDER-UNVERIFIED). Wyniki zależą od nich – traktuj je ostrożnie.
              </p>
            )}
            <ul className="assumptions">
              {sim.assumptions.map((a) => (
                <li key={a.key} className={isPlaceholder(a.status) ? "assumption placeholder" : "assumption"}>
                  <code>{a.key}</code>
                  {a.value !== null && <> = {numFmt.format(a.value)}</>}{" "}
                  <span className={isPlaceholder(a.status) ? "badge badge-warn" : "badge"}>{a.status}</span>
                  <small>{a.note}</small>
                </li>
              ))}
            </ul>
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
