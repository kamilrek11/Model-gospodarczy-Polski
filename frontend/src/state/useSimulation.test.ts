import { renderHook, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSimulation } from "./useSimulation";

const okBody = { years: [2026], taxes: {}, total: {}, model_version: "x" };

function jsonResponse(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

describe("useSimulation", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("debounces 300ms and aborts previous request", async () => {
    const signals: AbortSignal[] = [];
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
      signals.push(init!.signal!);
      return new Promise<Response>(() => {}); // never resolves
    });
    vi.stubGlobal("fetch", fetchMock);

    const { rerender, result } = renderHook(({ p }) => useSimulation(p), {
      initialProps: { p: { a: 1 } },
    });
    expect(result.current.loading).toBe(true);
    await act(async () => {
      vi.advanceTimersByTime(299);
    });
    expect(fetchMock).not.toHaveBeenCalled();
    rerender({ p: { a: 2 } });
    await act(async () => {
      vi.advanceTimersByTime(299);
    });
    expect(fetchMock).not.toHaveBeenCalled(); // timer restarted
    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/simulate");
    expect(JSON.parse(fetchMock.mock.calls[0][1]!.body as string).params).toEqual({ a: 2 });

    rerender({ p: { a: 3 } });
    await act(async () => {
      vi.advanceTimersByTime(300);
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(signals[0].aborted).toBe(true);
    expect(signals[1].aborted).toBe(false);
  });

  it("returns result on success", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse(200, okBody)));
    const { result } = renderHook(() => useSimulation({ a: 1 }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    expect(result.current.result).toEqual(okBody);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("maps 409 to no-data", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse(409, { detail: "brak danych – uruchom odświeżenie" })));
    const { result } = renderHook(() => useSimulation({ a: 1 }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    expect(result.current.error?.kind).toBe("no-data");
    expect(result.current.loading).toBe(false);
  });

  it("maps 422 to invalid and network failure to network", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse(422, { detail: "zły parametr" })));
    const a = renderHook(() => useSimulation({ a: 1 }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    expect(a.result.current.error).toMatchObject({ kind: "invalid", message: "zły parametr" });

    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    const b = renderHook(() => useSimulation({ a: 1 }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    expect(b.result.current.error?.kind).toBe("network");
  });

  it("aborted request never sets state", async () => {
    const resolvers: Array<(r: Response) => void> = [];
    const fetchMock = vi.fn((_u: string, init?: RequestInit) => {
      // ignores abort signal on purpose: a late response must still be discarded
      void init;
      return new Promise<Response>((res) => resolvers.push(res));
    });
    vi.stubGlobal("fetch", fetchMock);
    const { rerender, result } = renderHook(({ p }) => useSimulation(p), {
      initialProps: { p: { a: 1 } },
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    rerender({ p: { a: 2 } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    expect(resolvers).toHaveLength(2);
    await act(async () => {
      resolvers[0](new Response(JSON.stringify({ ...okBody, model_version: "stale" }), { status: 200 }));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.result).toBeNull();
    expect(result.current.loading).toBe(true);
    await act(async () => {
      resolvers[1](new Response(JSON.stringify({ ...okBody, model_version: "fresh" }), { status: 200 }));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.result?.model_version).toBe("fresh");
  });

  it("does not set state when aborted request rejects", async () => {
    const fetchMock = vi.fn((_u: string, init?: RequestInit) => {
      return new Promise<Response>((_res, rej) => {
        init!.signal!.addEventListener("abort", () => rej(new DOMException("aborted", "AbortError")));
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const { rerender, result } = renderHook(({ p }) => useSimulation(p), {
      initialProps: { p: { a: 1 } },
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    rerender({ p: { a: 2 } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.error).toBeNull();
  });
});
