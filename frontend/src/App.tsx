import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getParameters } from "./api/client";
import type { ParamSpec } from "./api/types";
import type { TaxKey } from "./api/types";
import { BudgetStack } from "./charts/BudgetStack";
import { ForecastVsActual } from "./charts/ForecastVsActual";
import { CompareView } from "./components/CompareView";
import { ChartSkeleton } from "./components/ChartSkeleton";
import { DisabledNotice } from "./components/DisabledNotice";
import { EmptyState } from "./components/EmptyState";
import { ExportBar } from "./components/ExportBar";
import { ParameterPanel } from "./components/ParameterPanel";
import { QualityTab } from "./components/QualityTab";
import { ScenarioBar } from "./components/ScenarioBar";
import { StatusBanner } from "./components/StatusBanner";
import { ThemeToggle } from "./components/ThemeToggle";
import { useHistory } from "./state/useHistory";
import { useRefresh } from "./state/useRefresh";
import { useSimulation } from "./state/useSimulation";

type TabId = "sim" | "compare" | "quality";
const TABS: { id: TabId; label: string }[] = [
  { id: "sim", label: "Symulacja" },
  { id: "compare", label: "Porównanie scenariuszy" },
  { id: "quality", label: "Jakość modelu" },
];

export default function App() {
  const [schema, setSchema] = useState<ParamSpec[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<Record<string, number>>({});

  useEffect(() => {
    const c = new AbortController();
    getParameters(c.signal)
      .then(setSchema)
      .catch((e: unknown) => {
        if (!c.signal.aborted) setLoadError(e instanceof Error ? e.message : "Błąd ładowania parametrów");
      });
    return () => c.abort();
  }, []);

  const values = useMemo(() => {
    const base = Object.fromEntries((schema ?? []).map((s) => [s.key, s.default]));
    return { ...base, ...overrides };
  }, [schema, overrides]);

  const onChange = useCallback((key: string, value: number) => setOverrides((o) => ({ ...o, [key]: value })), []);
  const onReset = useCallback(() => setOverrides({}), []);

  const limits = useMemo(() => new Map((schema ?? []).map((p) => [p.key, { min: p.min, max: p.max }])), [schema]);
  // ScenarioBar przekazuje już oczyszczone parametry (nieznane klucze pominięte, wartości przycięte do min/max).
  const onLoadScenario = useCallback((params: Record<string, number>) => setOverrides(params), []);
  const [tab, setTab] = useState<TabId>("sim");
  const resultsRef = useRef<HTMLDivElement>(null);
  const getCharts = useCallback(() => Array.from(resultsRef.current?.querySelectorAll(".chart-frame svg.recharts-surface") ?? []), []);

  const [tax, setTax] = useState<TaxKey>("pit");
  const [reloadKey, setReloadKey] = useState(0);
  const onRefreshDone = useCallback(() => setReloadKey((k) => k + 1), []);
  const refresh = useRefresh(onRefreshDone);
  const { result, loading, error } = useSimulation(schema ? values : null, { refreshKey: reloadKey });
  const { history, error: historyError } = useHistory(reloadKey);

  const noData = error?.kind === "no-data" || (historyError?.kind === "no-data" && !history);
  const otherError = error && error.kind !== "no-data" ? error : historyError && historyError.kind !== "no-data" ? historyError : null;
  const updatedAt = result?.data_updated_at ?? refresh.status?.updated_at ?? null;

  return (
    <div className="app">
      <header className="topbar">
        <h1>Symulator wpływów budżetowych</h1>
        <ThemeToggle />
      </header>
      <div className="layout">
        <aside className="sidebar" aria-label="Parametry">
          {loadError && <p role="alert">{loadError}</p>}
          {schema && <ParameterPanel schema={schema} values={values} onChange={onChange} onReset={onReset} />}
          {schema && <ScenarioBar params={values} limits={limits} onLoad={onLoadScenario} />}
        </aside>
        <main className="content">
          <StatusBanner error={otherError?.kind === "invalid" ? null : otherError} status={refresh.status} updatedAt={updatedAt} onRefresh={refresh.start} />
          <div className="tabs" role="tablist" aria-label="Widoki">
            {TABS.map((t) => (
              <button key={t.id} type="button" role="tab" id={`tab-${t.id}`} aria-selected={tab === t.id} aria-controls={`panel-${t.id}`} onClick={() => setTab(t.id)}>
                {t.label}
              </button>
            ))}
          </div>
          <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
            {tab === "sim" && (
              <>
                <ExportBar result={result} params={values} getCharts={getCharts} />
                {error?.kind === "invalid" && <p role="alert">{error.message}</p>}
                {noData ? (
                  <EmptyState status={refresh.status} onRefresh={refresh.start} />
                ) : result && history ? (
                  <div ref={resultsRef} className={loading ? "results stale" : "results"} aria-busy={loading}>
                    <DisabledNotice modules={result.disabled_modules} />
                    <ForecastVsActual tax={tax} history={history} sim={result} onTaxChange={setTax} />
                    <BudgetStack sim={result} history={history} />
                  </div>
                ) : (
                  <ChartSkeleton />
                )}
              </>
            )}
            {tab === "compare" && schema && <CompareView limits={limits} />}
            {tab === "quality" && <QualityTab sim={result} refreshKey={reloadKey} />}
          </div>
        </main>
      </div>
    </div>
  );
}
