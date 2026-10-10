import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { POLL_MS } from "../state/useRefresh";
import { history, sim } from "../testFixtures";
import { BudgetStack } from "./BudgetStack";
import { bridgeForecast, buildForecastSeries, buildStackRows, changeVsBaseline } from "./data";
import { ForecastVsActual } from "./ForecastVsActual";

describe("data transformations", () => {
  it("buildForecastSeries joins realised history with forecast bands", () => {
    const rows = buildForecastSeries(history, sim, "pit");
    expect(rows.map((r) => r.year)).toEqual([2023, 2024, 2025, 2026, 2027]);
    expect(rows[0]).toMatchObject({ year: 2023, actual: 90, forecast: false });
    expect(rows[0].median).toBeUndefined();
    expect(rows[4]).toMatchObject({ year: 2027, median: 110.5, band80: [107.5, 113.5], band95: [105.5, 115.5], forecast: true });
    expect(rows[4].actual).toBeUndefined();
  });

  it("changeVsBaseline computes last-year and horizon-total deltas", () => {
    const c = changeVsBaseline(sim, "pit")!;
    expect(c.lastYear).toBe(2027);
    expect(c.lastDelta).toBeCloseTo(2.5);
    expect(c.lastPct).toBeCloseTo(2.3148, 3);
    expect(c.totalDelta).toBeCloseTo(2.5);
    expect(c.totalPct).toBeCloseTo((2.5 / 208) * 100, 5);
    expect(changeVsBaseline({ ...sim, taxes: {} }, "pit")).toBeNull();
  });

  it("buildStackRows omits hidden series and marks forecast years", () => {
    const rows = buildStackRows(history, sim, new Set(["cit"]));
    expect(rows.map((r) => r.year)).toEqual([2023, 2024, 2025, 2026, 2027]);
    expect(rows[2]).toEqual({ year: 2025, forecast: false, pit: 100, vat: 300 });
    expect(rows[3]).toEqual({ year: 2026, forecast: true, pit: 100, vat: 310 });
  });
});

describe("year overlap and gaps", () => {
  const overlapHistory = { ...history, pit: [...history.pit!, { year: 2026, value: 101 }] };
  const gapSim = { ...sim, years: [2028, 2029] };

  it("buildForecastSeries keeps one row per year; overlap row has actual and median", () => {
    const rows = buildForecastSeries(overlapHistory, sim, "pit");
    expect(rows.map((r) => r.year)).toEqual([2023, 2024, 2025, 2026, 2027]);
    expect(rows[3]).toMatchObject({ year: 2026, actual: 101, median: 100, forecast: true });
  });

  it("buildForecastSeries leaves gap years out without NaN", () => {
    const rows = buildForecastSeries(history, gapSim, "pit");
    expect(rows.map((r) => r.year)).toEqual([2023, 2024, 2025, 2028, 2029]);
    expect(JSON.stringify(rows)).not.toMatch(/NaN|null/);
    const bridged = bridgeForecast(rows);
    expect(bridged[2]).toMatchObject({ year: 2025, actual: 100, median: 100 });
  });

  it("bridgeForecast does nothing for an overlap row", () => {
    const rows = buildForecastSeries(overlapHistory, sim, "pit");
    expect(bridgeForecast(rows)).toBe(rows);
  });

  it("buildStackRows: realised wins in overlap year and is not flagged forecast", () => {
    const rows = buildStackRows(overlapHistory, sim, new Set());
    expect(rows.map((r) => r.year)).toEqual([2023, 2024, 2025, 2026, 2027]);
    expect(rows[3]).toEqual({ year: 2026, forecast: false, pit: 101 });
    expect(rows[4]).toEqual({ year: 2027, forecast: true, pit: 110.5, cit: 66, vat: 320 });
  });

  it("buildStackRows: gap year yields no row; no-overlap unchanged", () => {
    const rows = buildStackRows(history, gapSim, new Set());
    expect(rows.map((r) => r.year)).toEqual([2023, 2024, 2025, 2028, 2029]);
    expect(rows.every((r) => Object.values(r).every((v) => v === true || v === false || Number.isFinite(v)))).toBe(true);
  });

  it("tables show one row per year and realised value for the overlap year", () => {
    render(<ForecastVsActual tax="pit" history={overlapHistory} sim={sim} />);
    const t1 = screen.getByRole("table", { name: /PIT/ });
    expect(within(t1).getAllByRole("rowheader").map((h) => h.textContent)).toEqual(["2023", "2024", "2025", "2026", "2027"]);
    render(<BudgetStack sim={sim} history={overlapHistory} />);
    const t2 = screen.getAllByRole("table")[1];
    const row2026 = within(t2).getByRole("rowheader", { name: "2026" }).closest("tr")!;
    expect(row2026).toHaveTextContent("101,00");
    expect(row2026).toHaveTextContent("wykonanie");
  });
});

describe("ForecastVsActual", () => {
  it("ForecastVsActual shows change vs baseline in mld zł and %", () => {
    render(<ForecastVsActual tax="pit" history={history} sim={sim} />);
    const row = screen.getByTestId("metric-row");
    expect(row).toHaveTextContent("Zmiana vs baza, ostatni rok prognozy (2027)");
    expect(row).toHaveTextContent("+2,50 mld zł");
    expect(row).toHaveTextContent("+2,3%");
    expect(row).toHaveTextContent("Suma za horyzont (2026–2027)");
    expect(row).toHaveTextContent("+1,2%");
  });

  it("tax selector switches the tax and offers a data table", async () => {
    const onTaxChange = vi.fn();
    render(<ForecastVsActual tax="pit" history={history} sim={sim} onTaxChange={onTaxChange} />);
    expect(screen.getByRole("button", { name: "PIT" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: "VAT" }));
    expect(onTaxChange).toHaveBeenCalledWith("vat");
    const table = screen.getByRole("table", { name: /PIT/ });
    expect(within(table).getAllByRole("rowheader")).toHaveLength(5);
    expect(within(table).getByRole("rowheader", { name: "2027" })).toBeInTheDocument();
  });

  it("renders the svg chart when the container has width", () => {
    const spy = vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(600);
    const warn = vi.spyOn(console, "warn");
    const err = vi.spyOn(console, "error");
    const { container } = render(<ForecastVsActual tax="pit" history={history} sim={sim} />);
    expect(container.querySelector("svg.recharts-surface")).not.toBeNull();
    expect(warn).not.toHaveBeenCalled();
    expect(err).not.toHaveBeenCalled();
    spy.mockRestore();
    warn.mockRestore();
    err.mockRestore();
  });
});

describe("BudgetStack", () => {
  it("BudgetStack legend toggles series", async () => {
    render(<BudgetStack sim={sim} history={history} />);
    const pit = screen.getByRole("button", { name: "PIT" });
    expect(pit).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(pit);
    expect(pit).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "CIT" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(pit);
    expect(pit).toHaveAttribute("aria-pressed", "true");
  });

  it("notes that other revenue types arrive in v2 and provides a table", () => {
    render(<BudgetStack sim={sim} history={history} />);
    expect(screen.getByText(/pozostałe rodzaje wpływów/i)).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getByRole("rowheader", { name: "2026" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "VAT" })).toBeInTheDocument();
  });
});

describe("App states", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("EmptyState shown on 409 with refresh button", async () => {
    const params = [{ key: "vat_rate", label: "Stawka VAT", tax: "vat", unit: "ułamek", default: 0.23, min: 0, max: 0.4, step: 0.01, description: "x" }];
    const no = () => new Response(JSON.stringify({ detail: "brak danych – uruchom odświeżenie" }), { status: 409 });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.endsWith("/parameters")) return new Response(JSON.stringify(params), { status: 200 });
        if (url.endsWith("/refresh/status")) return new Response(JSON.stringify({ state: "idle", errors: {}, updated_at: null }), { status: 200 });
        return no();
      }),
    );
    render(<App />);
    const empty = (await screen.findByText(/brak danych/i)).closest(".empty-state") as HTMLElement;
    expect(empty).toBeInTheDocument();
    // EmptyState has its own refresh button (the top bar has another one, see App.test.tsx)
    expect(within(empty).getByRole("button", { name: "Odśwież dane" })).toBeEnabled();
  });

  it("after refresh done, history and simulation are refetched and charts shown", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const params = [{ key: "vat_rate", label: "Stawka VAT", tax: "vat", unit: "ułamek", default: 0.23, min: 0, max: 0.4, step: 0.01, description: "x" }];
      let refreshed = false;
      let polls = 0;
      const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status });
      const calls: string[] = [];
      vi.stubGlobal(
        "fetch",
        vi.fn(async (url: string, init?: RequestInit) => {
          calls.push(`${init?.method ?? "GET"} ${url}`);
          if (url.endsWith("/parameters")) return json(params);
          if (url.endsWith("/refresh") && init?.method === "POST") return json({ state: "running" }, 202);
          if (url.endsWith("/refresh/status")) {
            const state = polls++ === 0 ? "idle" : "done";
            if (state === "done") refreshed = true;
            return json({ state, errors: {}, updated_at: "2026-10-09T12:00:00Z" });
          }
          if (!refreshed) return json({ detail: "brak danych – uruchom odświeżenie" }, 409);
          return url.endsWith("/history") ? json(history) : json(sim);
        }),
      );
      render(<App />);
      const btn = await screen.findByRole("button", { name: "Odśwież dane" });
      await act(async () => btn.click());
      await act(async () => vi.advanceTimersByTimeAsync(POLL_MS + 1000));
      expect(await screen.findByRole("group", { name: "Wybór podatku" })).toBeInTheDocument();
      expect(screen.getByTestId("metric-row")).toHaveTextContent("mld zł");
      expect(calls.filter((c) => c === "GET /api/history").length).toBeGreaterThanOrEqual(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("server status done on mount does not trigger a second history/simulate load", async () => {
    const params = [{ key: "vat_rate", label: "Stawka VAT", tax: "vat", unit: "ułamek", default: 0.23, min: 0, max: 0.4, step: 0.01, description: "x" }];
    const json = (b: unknown) => new Response(JSON.stringify(b), { status: 200 });
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push(`${init?.method ?? "GET"} ${url}`);
        if (url.endsWith("/parameters")) return json(params);
        if (url.endsWith("/refresh/status")) return json({ state: "done", errors: {}, updated_at: "2026-10-09T12:00:00Z" });
        return url.endsWith("/history") ? json(history) : json(sim);
      }),
    );
    render(<App />);
    expect(await screen.findByTestId("metric-row")).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 500));
    expect(calls.filter((c) => c === "GET /api/history")).toHaveLength(1);
    expect(calls.filter((c) => c === "POST /api/simulate")).toHaveLength(1);
  });
});
