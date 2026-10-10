import { useEffect, useState } from "react";
import { ApiError, simulate } from "../api/client";
import type { SimulationResult } from "../api/types";

export const DEBOUNCE_MS = 300;
/**
 * Wspólne ziarno losowań Monte Carlo dla widoku Symulacja i Porównanie: ten sam scenariusz
 * daje te same mediany w obu widokach, a różnice wynikają wyłącznie z parametrów.
 */
export const SIMULATION_SEED = 1;

export interface SimulationOptions {
  horizon?: number;
  nPaths?: number;
  seed?: number;
  /** Zmiana wartości wymusza ponowne obliczenie (np. po odświeżeniu danych). */
  refreshKey?: number;
}

export interface UseSimulation {
  result: SimulationResult | null;
  loading: boolean;
  error: ApiError | null;
}

/** Symulacja z debounce 300 ms; poprzednie żądanie jest anulowane (AbortController). */
export function useSimulation(
  params: Record<string, number> | null,
  { horizon = 5, nPaths = 1000, seed = SIMULATION_SEED, refreshKey = 0 }: SimulationOptions = {},
): UseSimulation {
  // Zawartość parametrów (nie tożsamość obiektu) decyduje o ponownym uruchomieniu.
  const paramsKey = params === null ? null : JSON.stringify(params);
  const [state, setState] = useState<UseSimulation>({ result: null, loading: params !== null, error: null });

  useEffect(() => {
    if (paramsKey === null) return;
    const parsed = JSON.parse(paramsKey) as Record<string, number>;
    const controller = new AbortController();
    setState((s) => ({ ...s, loading: true }));
    const timer = setTimeout(() => {
      simulate({ params: parsed, horizon, n_paths: nPaths, seed }, controller.signal)
        .then((result) => {
          if (controller.signal.aborted) return;
          setState({ result, loading: false, error: null });
        })
        .catch((e: unknown) => {
          if (controller.signal.aborted) return;
          const error = e instanceof ApiError ? e : new ApiError("network", "Brak połączenia z serwerem");
          setState((s) => ({ ...s, loading: false, error }));
        });
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [paramsKey, horizon, nPaths, seed, refreshKey]);

  return state;
}
