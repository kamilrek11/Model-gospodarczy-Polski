import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, getRefreshStatus, startRefresh } from "../api/client";
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
  /** Trwa start lub odpytywanie – kolejne start() jest ignorowane. */
  const busy = useRef(false);
  /** Odświeżenie uruchomione tu lub zaobserwowane jako running – tylko wtedy wołamy onDone. */
  const watching = useRef(false);
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
        busy.current = true;
        watching.current = true;
        timer.current = setTimeout(poll, POLL_MS);
        return;
      }
      busy.current = false;
      if (s.state === "done" && watching.current) onDoneRef.current();
      watching.current = false;
    } catch (e) {
      if (!alive.current || c.signal.aborted) return;
      busy.current = false;
      watching.current = false;
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
    if (busy.current) return;
    busy.current = true;
    try {
      await startRefresh();
    } catch (e) {
      // Backend zwraca 409 wyłącznie, gdy zadanie już trwa (api/refresh.py) – to nie błąd, tylko dołączamy do odpytywania.
      if (e instanceof ApiError && e.kind === "disabled") {
        // 403: odświeżanie wyłączone w tej instancji – żadne zadanie nie ruszyło, nie odpytujemy
        busy.current = false;
        if (alive.current) setStatus((s) => ({ state: "failed", errors: { refresh: e.message }, updated_at: s?.updated_at ?? null, synthetic: s?.synthetic, disabled: true }));
        return;
      }
      if (!(e instanceof ApiError && e.kind === "no-data")) {
        busy.current = false;
        if (alive.current) setStatus({ state: "failed", errors: { refresh: e instanceof Error ? e.message : "Błąd uruchomienia odświeżenia" }, updated_at: null });
        return;
      }
    }
    if (!alive.current) return;
    watching.current = true;
    setStatus((s) => ({ state: "running", errors: {}, updated_at: s?.updated_at ?? null }));
    stop();
    timer.current = setTimeout(poll, POLL_MS);
  }, [poll, stop]);

  return { status, start };
}
