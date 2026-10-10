import { useEffect, useState } from "react";
import { ApiError, getHistory } from "../api/client";
import type { HistoryData } from "../api/types";

export interface UseHistory {
  history: HistoryData | null;
  error: ApiError | null;
}

/** Historia wpływów (GET /history); `reloadKey` wymusza ponowne pobranie (po odświeżeniu danych). */
export function useHistory(reloadKey = 0): UseHistory {
  const [state, setState] = useState<UseHistory>({ history: null, error: null });
  useEffect(() => {
    const c = new AbortController();
    getHistory(c.signal)
      .then((history) => !c.signal.aborted && setState({ history, error: null }))
      .catch((e: unknown) => {
        if (c.signal.aborted) return;
        setState((s) => ({ ...s, error: e instanceof ApiError ? e : new ApiError("network", "Brak połączenia z serwerem") }));
      });
    return () => c.abort();
  }, [reloadKey]);
  return state;
}
