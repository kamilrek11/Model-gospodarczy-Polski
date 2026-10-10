import { useCallback, useEffect, useMemo, useState } from "react";
import { getParameters } from "./api/client";
import type { ParamSpec } from "./api/types";
import type { TaxKey } from "./api/types";
import { BudgetStack } from "./charts/BudgetStack";
import { ForecastVsActual } from "./charts/ForecastVsActual";
import { ChartSkeleton } from "./components/ChartSkeleton";
import { DisabledNotice } from "./components/DisabledNotice";
import { EmptyState } from "./components/EmptyState";
import { ParameterPanel } from "./components/ParameterPanel";
import { StatusBanner } from "./components/StatusBanner";
import { useHistory } from "./state/useHistory";
import { useRefresh } from "./state/useRefresh";
import { useSimulation } from "./state/useSimulation";

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
      </header>
      <div className="layout">
        <aside className="sidebar" aria-label="Parametry">
          {loadError && <p role="alert">{loadError}</p>}
          {schema && <ParameterPanel schema={schema} values={values} onChange={onChange} onReset={onReset} />}
        </aside>
        <main className="content">
          <StatusBanner error={otherError?.kind === "invalid" ? null : otherError} status={refresh.status} updatedAt={updatedAt} onRefresh={refresh.start} />
          {error?.kind === "invalid" && <p role="alert">{error.message}</p>}
          {noData ? (
            <EmptyState status={refresh.status} onRefresh={refresh.start} />
          ) : result && history ? (
            <div className={loading ? "results stale" : "results"} aria-busy={loading}>
              <DisabledNotice modules={result.disabled_modules} />
              <ForecastVsActual tax={tax} history={history} sim={result} onTaxChange={setTax} />
              <BudgetStack sim={result} history={history} />
            </div>
          ) : (
            <ChartSkeleton />
          )}
        </main>
      </div>
    </div>
  );
}
