import { useCallback, useEffect, useMemo, useState } from "react";
import { getParameters } from "./api/client";
import type { ParamSpec } from "./api/types";
import { ParameterPanel } from "./components/ParameterPanel";
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

  const { result, loading, error } = useSimulation(schema ? values : null);

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
          {error && <p role="alert">{error.message}</p>}
          {loading && <p>Obliczanie…</p>}
          {result && !error && <p>Wyniki gotowe (wykresy w kolejnym kroku).</p>}
        </main>
      </div>
    </div>
  );
}
