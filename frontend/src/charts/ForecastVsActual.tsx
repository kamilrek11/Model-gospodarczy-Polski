import { Area, CartesianGrid, ComposedChart, Line, Tooltip, XAxis, YAxis } from "recharts";
import type { HistoryData, SimulationResult, TaxKey } from "../api/types";
import { DataTable } from "../components/DataTable";
import { fmtAxis, fmtMld, fmtPct, fmtSignedMld } from "../format";
import { ChartFrame } from "./ChartFrame";
import { bridgeForecast, buildForecastSeries, changeVsBaseline } from "./data";
import { INK, TAX_COLOR, TAX_LABEL, TAX_ORDER } from "./palette";

interface Props {
  tax: TaxKey;
  history: HistoryData;
  sim: SimulationResult;
  onTaxChange?: (tax: TaxKey) => void;
}

const HEIGHT = 340;

export function ForecastVsActual({ tax, history, sim, onTaxChange }: Props) {
  const rows = buildForecastSeries(history, sim, tax);
  const change = changeVsBaseline(sim, tax);
  const color = TAX_COLOR[tax];
  const name = TAX_LABEL[tax];
  const chartRows = bridgeForecast(rows);

  const metric = (label: string, delta: number, pct: number | null) => (
    <div className="metric">
      <span className="metric-label">{label}</span>
      <span className="metric-value">
        {fmtSignedMld(delta)} mld zł{pct !== null && <> ({fmtPct(pct)})</>}
      </span>
    </div>
  );

  return (
    <section className="viz-card" aria-labelledby="fva-title">
      <h2 id="fva-title">Wpływy z {name}: wykonanie i prognoza</h2>
      <div className="seg" role="group" aria-label="Wybór podatku">
        {TAX_ORDER.map((t) => (
          <button key={t} type="button" aria-pressed={t === tax} onClick={() => onTaxChange?.(t)}>
            {TAX_LABEL[t]}
          </button>
        ))}
      </div>

      <div className="metric-row" data-testid="metric-row">
        {change ? (
          <>
            {metric(`Zmiana vs baza, ostatni rok prognozy (${change.lastYear})`, change.lastDelta, change.lastPct)}
            {metric(`Suma za horyzont (${change.firstYear}–${change.lastYear})`, change.totalDelta, change.totalPct)}
          </>
        ) : (
          <span className="metric-label">Brak prognozy dla tego podatku (moduł wyłączony).</span>
        )}
      </div>

      <ChartFrame height={HEIGHT} label={`Wykres: wpływy z ${name} w mld zł, wykonanie (linia ciągła) i prognoza (linia przerywana z pasmami 80% i 95%)`}>
        {(width) => (
          <ComposedChart width={width} height={HEIGHT} data={chartRows} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
            <CartesianGrid stroke={INK.grid} vertical={false} />
            <XAxis dataKey="year" tick={{ fill: INK.secondary, fontSize: 12 }} stroke={INK.grid} />
            <YAxis
              width={56}
              domain={["auto", "auto"]}
              tickFormatter={fmtAxis}
              tick={{ fill: INK.secondary, fontSize: 12 }}
              stroke={INK.grid}
              label={{ value: "mld zł", angle: -90, position: "insideLeft", fill: INK.secondary, fontSize: 12 }}
            />
            <Tooltip
              contentStyle={{ background: INK.surface, border: `1px solid ${INK.grid}`, color: INK.primary }}
              formatter={(v) => (Array.isArray(v) ? `${fmtMld(Number(v[0]))} – ${fmtMld(Number(v[1]))} mld zł` : `${fmtMld(Number(v))} mld zł`)}
            />
            <Area type="monotone" dataKey="band95" name="Pasmo 95%" stroke="none" fill={color} fillOpacity={0.12} isAnimationActive={false} />
            <Area type="monotone" dataKey="band80" name="Pasmo 80%" stroke="none" fill={color} fillOpacity={0.24} isAnimationActive={false} />
            <Line type="monotone" dataKey="actual" name="Wykonanie" stroke={color} strokeWidth={2} dot={{ r: 4, stroke: INK.surface, strokeWidth: 2, fill: color }} isAnimationActive={false} connectNulls />
            <Line type="monotone" dataKey="median" name="Prognoza (mediana)" stroke={color} strokeWidth={2} strokeDasharray="6 4" dot={false} isAnimationActive={false} connectNulls />
          </ComposedChart>
        )}
      </ChartFrame>

      <ul className="key" aria-label="Legenda wykresu">
        <li><span className="key-line" style={{ borderTopColor: color }} /> Wykonanie</li>
        <li><span className="key-line dashed" style={{ borderTopColor: color }} /> Prognoza (mediana)</li>
        <li><span className="key-band b80" style={{ background: color }} /> Pasmo 80% (p10–p90)</li>
        <li><span className="key-band b95" style={{ background: color }} /> Pasmo 95% (p2,5–p97,5)</li>
      </ul>

      <DataTable
        caption={`${name}: wykonanie i prognoza, mld zł`}
        columns={["Rok", "Wykonanie", "Prognoza (mediana)", "Pasmo 80%", "Pasmo 95%"]}
        rows={rows.map((r) => [
          String(r.year),
          r.actual !== undefined ? fmtMld(r.actual) : "–",
          r.median !== undefined ? fmtMld(r.median) : "–",
          r.band80 ? `${fmtMld(r.band80[0])} – ${fmtMld(r.band80[1])}` : "–",
          r.band95 ? `${fmtMld(r.band95[0])} – ${fmtMld(r.band95[1])}` : "–",
        ])}
      />
    </section>
  );
}
