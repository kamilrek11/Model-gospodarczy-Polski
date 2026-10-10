import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { POLL_MS, useRefresh } from "./useRefresh";

function mockFetch(states: Array<{ state: string; errors?: Record<string, string> }>) {
  let i = 0;
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (url.endsWith("/refresh") && init?.method === "POST") return new Response(JSON.stringify({ state: "running" }), { status: 202 });
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
});
