import { useCallback, useEffect, useRef, useState } from "react";
import { getRefreshStatus, startRefresh } from "../api/client";
import type { RefreshStatus } from "../api/types";

export const POLL_MS = 2000;

export interface UseRefresh {
  status: RefreshStatus | null;
  start: () => Promise<void>;
}

/** Uruchamia odświeżenie danych i odpytuje /refresh/status do stanu done/failed (lub odmontowania). */
export function useRefresh(onDone: () => void): UseRefresh {
  const [status, setStatus] = useState<RefreshStatus | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const alive = useRef(false);
  const controller = useRef<AbortController | null>(null);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  const stop = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    controller.current?.abort();
  }, []);

  const poll = useCallback(async () => {
    const c = new AbortController();
    controller.current = c;
    try {
      const s = await getRefreshStatus(c.signal);
      if (!alive.current || c.signal.aborted) return;
      setStatus(s);
      if (s.state === "running") {
        timer.current = setTimeout(poll, POLL_MS);
      } else if (s.state === "done") {
        onDoneRef.current();
      }
    } catch (e) {
      if (!alive.current || c.signal.aborted) return;
      setStatus({ state: "failed", errors: { status: e instanceof Error ? e.message : "Błąd odczytu statusu" }, updated_at: null });
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    void poll(); // stan początkowy (wznawia odpytywanie, jeśli odświeżanie już trwa)
    return () => {
      alive.current = false;
      stop();
    };
  }, [poll, stop]);

  const start = useCallback(async () => {
    try {
      await startRefresh();
    } catch (e) {
      if (alive.current) setStatus({ state: "failed", errors: { refresh: e instanceof Error ? e.message : "Błąd uruchomienia odświeżenia" }, updated_at: null });
      return;
    }
    if (!alive.current) return;
    setStatus((s) => ({ state: "running", errors: {}, updated_at: s?.updated_at ?? null }));
    stop();
    timer.current = setTimeout(poll, POLL_MS);
  }, [poll, stop]);

  return { status, start };
}
