import { useId, useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, Tooltip, XAxis, YAxis } from "recharts";
import { ApiError, simulate } from "../api/client";
import type { SimulationResult, TaxKey } from "../api/types";
import { ChartFrame } from "../charts/ChartFrame";
import { INK, TAX_LABEL, TAX_ORDER } from "../charts/palette";
import { fmtAxis, fmtMld, fmtPct, fmtSignedMld } from "../format";
import { compare } from "../scenarios/compare";
import { listScenarios, sanitizeParams, type ParamLimits } from "../scenarios/store";
import { SIMULATION_SEED } from "../state/useSimulation";

const SEED = SIMULATION_SEED; // wspólne losowania dla obu scenariuszy i widoku Symulacja – różnice pochodzą z parametrów

interface Pair {
  a: { name: string; result: SimulationResult };
  b: { name: string; result: SimulationResult };
}

export function CompareView({ limits }: { limits: ParamLimits }) {
  const id = useId();
  const scenarios = useMemo(listScenarios, []);
  const [nameA, setNameA] = useState("");
  const [nameB, setNameB] = useState("");
  const [pair, setPair] = useState<Pair | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState<string[]>([]);
  const [tax, setTax] = useState<TaxKey>("pit");

  const run = async () => {
    const sa = scenarios.find((s) => s.name === nameA);
    const sb = scenarios.find((s) => s.name === nameB);
    if (!sa || !sb) return;
    // Zapisane dane mogą być spoza schematu: nieznane klucze pomijamy, wartości przycinamy (jak przy wczytaniu).
    const ca = sanitizeParams(sa.params, limits);
    const cb = sanitizeParams(sb.params, limits);
    setNotes([...ca.notes.map((n) => `${sa.name}: ${n}`), ...cb.notes.map((n) => `${sb.name}: ${n}`)]);
    setLoading(true);
    setError(null);
    try {
      const [ra, rb] = await Promise.all([
        simulate({ params: ca.params, horizon: 5, n_paths: 1000, seed: SEED }),
        simulate({ params: cb.params, horizon: 5, n_paths: 1000, seed: SEED }),
      ]);
      setPair({ a: { name: sa.name, result: ra }, b: { name: sb.name, result: rb } });
    } catch (e) {
      setPair(null);
      setError(e instanceof ApiError ? e.message : "Nie udało się obliczyć porównania");
    } finally {
      setLoading(false);
    }
  };

  const rows = useMemo(() => (pair ? compare(pair.a.result, pair.b.result) : []), [pair]);
  const taxRows = rows.filter((r) => r.tax === tax);
  const chartRows = taxRows.map((r) => ({ year: r.year, a: r.a ?? undefined, b: r.b ?? undefined }));
  const availableTaxes = TAX_ORDER.filter((t) => rows.some((r) => r.tax === t));
  const dash = (v: number | null, f: (n: number) => string) => (v === null ? "–" : f(v));

  const select = (label: string, value: string, set: (v: string) => void, suffix: string) => (
    <div className="field">
      <label htmlFor={`${id}-${suffix}`}>{label}</label>
      <select id={`${id}-${suffix}`} value={value} onChange={(e) => set(e.target.value)}>
        <option value="">— wybierz —</option>
        {scenarios.map((s) => (
          <option key={s.name} value={s.name}>
            {s.name}
          </option>
        ))}
      </select>
    </div>
  );

  return (
    <div className="results">
      <section className="viz-card" aria-labelledby={`${id}-t`}>
        <h2 id={`${id}-t`}>Porównanie scenariuszy</h2>
        {scenarios.length < 2 ? (
          <p className="note">Zapisz co najmniej dwa scenariusze, aby je porównać.</p>
        ) : (
          <div className="controls">
            {select("Scenariusz A", nameA, setNameA, "a")}
            {select("Scenariusz B", nameB, setNameB, "b")}
            <button type="button" className="primary" onClick={() => void run()} disabled={!nameA || !nameB || loading}>
              {loading ? "Obliczanie…" : "Porównaj"}
            </button>
          </div>
        )}
        {notes.length > 0 && (
          <p className="note" role="status">
            Uwaga: {notes.join("; ")}.
          </p>
        )}
        {error && <p role="alert">{error}</p>}
      </section>

      {pair && (
        <section className="viz-card" aria-labelledby={`${id}-r`}>
          <h2 id={`${id}-r`}>
            {pair.a.name} a {pair.b.name}
          </h2>
          <div className="seg" role="group" aria-label="Wybór podatku">
            {availableTaxes.map((t) => (
              <button key={t} type="button" aria-pressed={t === tax} onClick={() => setTax(t)}>
                {TAX_LABEL[t]}
              </button>
            ))}
          </div>
          <ChartFrame height={300} label={`Mediany ${TAX_LABEL[tax]}: ${pair.a.name} i ${pair.b.name}`}>
            {(width) => (
              <LineChart width={width} height={300} data={chartRows} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                <CartesianGrid stroke={INK.grid} strokeDasharray="3 3" />
                <XAxis dataKey="year" stroke={INK.secondary} tick={{ fill: INK.secondary }} />
                <YAxis tickFormatter={fmtAxis} stroke={INK.secondary} tick={{ fill: INK.secondary }} unit=" mld" />
                <Tooltip formatter={(v) => `${fmtMld(Number(v))} mld zł`} />
                <Legend />
                <Line type="monotone" dataKey="a" name={pair.a.name} stroke="var(--series-1)" strokeWidth={2} dot isAnimationActive={false} connectNulls />
                <Line type="monotone" dataKey="b" name={pair.b.name} stroke="var(--series-2)" strokeWidth={2} strokeDasharray="6 3" dot isAnimationActive={false} connectNulls />
              </LineChart>
            )}
          </ChartFrame>
          <div className="table-scroll">
            <table className="data-table" data-testid="diff-table">
              <caption>Różnice median (B − A), mld zł</caption>
              <thead>
                <tr>
                  <th scope="col">Podatek</th>
                  <th scope="col">Rok</th>
                  <th scope="col">{pair.a.name}</th>
                  <th scope="col">{pair.b.name}</th>
                  <th scope="col">Różnica</th>
                  <th scope="col">Różnica %</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={`${r.tax}-${r.year}`}>
                    <th scope="row">{TAX_LABEL[r.tax]}</th>
                    <td>{r.year}</td>
                    <td>{dash(r.a, fmtMld)}</td>
                    <td>{dash(r.b, fmtMld)}</td>
                    <td>{dash(r.diff, fmtSignedMld)}</td>
                    <td>{dash(r.pct, fmtPct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

