import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
import type { HistoryData, SimulationResult, TaxKey } from "../api/types";
import { DataTable } from "../components/DataTable";
import { fmtAxis, fmtMld } from "../format";
import { ChartFrame } from "./ChartFrame";
import { buildStackRows } from "./data";
import { INK, TAX_COLOR, TAX_LABEL, TAX_ORDER } from "./palette";

const HEIGHT = 340;

export function BudgetStack({ sim, history }: { sim: SimulationResult; history: HistoryData }) {
  const [hidden, setHidden] = useState<ReadonlySet<TaxKey>>(new Set());
  const toggle = (t: TaxKey) =>
    setHidden((h) => {
      const n = new Set(h);
      if (n.has(t)) n.delete(t);
      else n.add(t);
      return n;
    });

  const rows = buildStackRows(history, sim, hidden);
  const all = buildStackRows(history, sim, new Set());
  const visible = TAX_ORDER.filter((t) => !hidden.has(t));

  return (
    <section className="viz-card" aria-labelledby="stack-title">
      <h2 id="stack-title">Wpływy budżetowe wg rodzaju (mld zł)</h2>
      <div className="seg legend" role="group" aria-label="Legenda – włącz lub wyłącz serię">
        {TAX_ORDER.map((t) => (
          <button key={t} type="button" aria-pressed={!hidden.has(t)} onClick={() => toggle(t)}>
            <span className="swatch" style={{ background: TAX_COLOR[t] }} aria-hidden="true" />
            {TAX_LABEL[t]}
          </button>
        ))}
      </div>

      <ChartFrame height={HEIGHT} label="Wykres słupkowy skumulowany: wpływy z PIT, CIT i VAT w kolejnych latach; lata prognozy to mediany">
        {(width) => (
          <BarChart width={width} height={HEIGHT} data={rows} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
            <CartesianGrid stroke={INK.grid} vertical={false} />
            <XAxis
              dataKey="year"
              tick={{ fill: INK.secondary, fontSize: 12 }}
              stroke={INK.grid}
              tickFormatter={(y: number) => (rows.find((r) => r.year === y)?.forecast ? `${y} (prog.)` : String(y))}
            />
            <YAxis width={56} tickFormatter={fmtAxis} tick={{ fill: INK.secondary, fontSize: 12 }} stroke={INK.grid} />
            <Tooltip
              cursor={{ fill: INK.grid, fillOpacity: 0.3 }}
              contentStyle={{ background: INK.surface, border: `1px solid ${INK.grid}`, color: INK.primary }}
              formatter={(v) => `${fmtMld(Number(v))} mld zł`}
            />
            {visible.map((t) => (
              <Bar key={t} dataKey={t} name={TAX_LABEL[t]} stackId="rev" fill={TAX_COLOR[t]} stroke={INK.surface} strokeWidth={1} isAnimationActive={false} />
            ))}
          </BarChart>
        )}
      </ChartFrame>

      <p className="note">
        Lata historyczne: wykonanie; lata prognozy (oznaczone „prog.”): mediana symulacji. W wersji 1 wykres obejmuje PIT, CIT i VAT;
        pozostałe rodzaje wpływów (np. akcyza, opłaty) pojawią się w wersji 2.
      </p>

      <DataTable
        caption="Wpływy z PIT, CIT i VAT wg lat, mld zł (wykonanie / mediana prognozy)"
        columns={["Rok", ...TAX_ORDER.map((t) => TAX_LABEL[t]), "Typ"]}
        rows={all.map((r) => [
          String(r.year),
          ...TAX_ORDER.map((t) => (r[t] !== undefined ? fmtMld(r[t]!) : "–")),
          r.forecast ? "prognoza" : "wykonanie",
        ])}
      />
    </section>
  );
}
