import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { POLL_MS, useRefresh } from "./useRefresh";

function mockFetch(states: Array<{ state: string; errors?: Record<string, string> }>, postStatus = 202) {
  let i = 0;
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (url.endsWith("/refresh") && init?.method === "POST") return new Response(JSON.stringify(postStatus === 409 ? { detail: "refresh already running" } : { state: "running" }), { status: postStatus });
      const s = states[Math.min(i++, states.length - 1)];
      return new Response(JSON.stringify({ errors: {}, updated_at: "2026-10-09T12:00:00Z", ...s }), { status: 200 });
    }),
  );
  return calls;
}

const statusCalls = (calls: string[]) => calls.filter((c) => c.endsWith("/refresh/status")).length;

describe("useRefresh polling", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("polling stops on done and calls onDone once", async () => {
    const calls = mockFetch([{ state: "idle" }, { state: "running" }, { state: "done" }]);
    const onDone = vi.fn();
    const { result } = renderHook(() => useRefresh(onDone));
    await act(async () => {}); // initial status load (idle)
    await act(async () => result.current.start());
    expect(result.current.status?.state).toBe("running");
    await act(async () => vi.advanceTimersByTimeAsync(POLL_MS));
    expect(result.current.status?.state).toBe("running");
    await act(async () => vi.advanceTimersByTimeAsync(POLL_MS));
    expect(result.current.status?.state).toBe("done");
    expect(onDone).toHaveBeenCalledTimes(1);
    const n = statusCalls(calls);
    await act(async () => vi.advanceTimersByTimeAsync(POLL_MS * 5));
    expect(statusCalls(calls)).toBe(n);
  });

  it("polling stops on failed and exposes error names", async () => {
    const calls = mockFetch([{ state: "idle" }, { state: "failed", errors: { gus_bdl: "timeout" } }]);
    const onDone = vi.fn();
    const { result } = renderHook(() => useRefresh(onDone));
    await act(async () => {});
    await act(async () => result.current.start());
    await act(async () => vi.advanceTimersByTimeAsync(POLL_MS));
    expect(result.current.status?.state).toBe("failed");
    expect(result.current.status?.errors).toEqual({ gus_bdl: "timeout" });
    expect(onDone).not.toHaveBeenCalled();
    const n = statusCalls(calls);
    await act(async () => vi.advanceTimersByTimeAsync(POLL_MS * 5));
    expect(statusCalls(calls)).toBe(n);
  });

  it("polling stops on unmount", async () => {
    const calls = mockFetch([{ state: "idle" }, { state: "running" }]);
    const { result, unmount } = renderHook(() => useRefresh(vi.fn()));
    await act(async () => {});
    await act(async () => result.current.start());
    unmount();
    const n = statusCalls(calls);
    await vi.advanceTimersByTimeAsync(POLL_MS * 5);
    expect(statusCalls(calls)).toBe(n);
  });

  it("409 from POST /refresh means already running: polls and fires onDone once", async () => {
    const calls = mockFetch([{ state: "idle" }, { state: "running" }, { state: "done" }], 409);
    const onDone = vi.fn();
    const { result } = renderHook(() => useRefresh(onDone));
    await act(async () => {});
    await act(async () => result.current.start());
    expect(result.current.status?.state).toBe("running");
    await act(async () => vi.advanceTimersByTimeAsync(POLL_MS));
    await act(async () => vi.advanceTimersByTimeAsync(POLL_MS));
    expect(result.current.status?.state).toBe("done");
    expect(onDone).toHaveBeenCalledTimes(1);
    const n = statusCalls(calls);
    await act(async () => vi.advanceTimersByTimeAsync(POLL_MS * 3));
    expect(statusCalls(calls)).toBe(n);
  });

  it("other POST errors stay failures", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => (init?.method === "POST" ? new Response("{}", { status: 500 }) : new Response(JSON.stringify({ state: "idle", errors: {}, updated_at: null }), { status: 200 }))));
    const { result } = renderHook(() => useRefresh(vi.fn()));
    await act(async () => {});
    await act(async () => result.current.start());
    expect(result.current.status?.state).toBe("failed");
  });

  it("two synchronous start() calls send exactly one POST", async () => {
    const calls = mockFetch([{ state: "idle" }, { state: "running" }]);
    const { result } = renderHook(() => useRefresh(vi.fn()));
    await act(async () => {});
    await act(async () => {
      void result.current.start();
      void result.current.start();
    });
    expect(calls.filter((c) => c.startsWith("POST")).length).toBe(1);
    expect(result.current.status?.state).toBe("running");
  });

  it("server status done on mount does not call onDone", async () => {
    mockFetch([{ state: "done" }]);
    const onDone = vi.fn();
    const { result } = renderHook(() => useRefresh(onDone));
    await act(async () => {});
    expect(result.current.status?.state).toBe("done");
    expect(onDone).not.toHaveBeenCalled();
  });

  it("running observed on mount then done calls onDone once", async () => {
    mockFetch([{ state: "running" }, { state: "done" }]);
    const onDone = vi.fn();
    renderHook(() => useRefresh(onDone));
    await act(async () => {});
    expect(onDone).not.toHaveBeenCalled();
    await act(async () => vi.advanceTimersByTimeAsync(POLL_MS));
    expect(onDone).toHaveBeenCalledTimes(1);
  });
});
