import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { sim } from "../testFixtures";
import { resetScenarioStore, saveScenario } from "../scenarios/store";
import { getStoredTheme, THEME_KEY } from "../theme";
import * as download from "../export/download";
import { CompareView } from "./CompareView";
import { ExportBar } from "./ExportBar";
import { QualityTab } from "./QualityTab";
import { ScenarioBar } from "./ScenarioBar";
import { ThemeToggle } from "./ThemeToggle";

const json = (b: unknown, status = 200, headers: Record<string, string> = {}) => new Response(JSON.stringify(b), { status, headers });

beforeEach(() => {
  localStorage.clear();
  resetScenarioStore();
  document.documentElement.removeAttribute("data-theme");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ThemeToggle", () => {
  it("applies data-theme, persists, and system removes it", async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);
    expect(document.documentElement).not.toHaveAttribute("data-theme");
    await user.click(screen.getByRole("button", { name: "Ciemny" }));
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    await user.click(screen.getByRole("button", { name: "Jasny" }));
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    await user.click(screen.getByRole("button", { name: "Systemowy" }));
    expect(document.documentElement).not.toHaveAttribute("data-theme");
    expect(localStorage.getItem(THEME_KEY)).toBeNull();
  });

  it("restores the stored theme on mount", () => {
    localStorage.setItem(THEME_KEY, "dark");
    render(<ThemeToggle />);
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(screen.getByRole("button", { name: "Ciemny" })).toHaveAttribute("aria-pressed", "true");
  });

  it("works when localStorage throws", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(getStoredTheme()).toBe("system");
    render(<ThemeToggle />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Ciemny" }));
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  });
});

describe("QualityTab", () => {
  const bt = {
    mape: { pit: 4.25, cit: 9.5 },
    coverage80: { pit: 0.8, cit: 0.6 },
    coverage95: { pit: 0.95, cit: 0.9 },
    notes: ["Backtest liczy lata historyczne przy obecnym prawie."],
    message: null,
    n_origins: 7,
    n_skipped: 2,
  };
  const simWith = {
    ...sim,
    assumptions: [
      { key: "vat.split", value: 0.5, status: "assumption", note: "rough split" },
      { key: "cit.base", value: 1.2, status: "sourced", note: "GUS" },
    ],
    calibration: { pit: { factor: 1.0345, years: [2022, 2023, 2024], method: "mediana" } },
  };

  it("renders backtest numbers, notes, assumptions and the assumption marker", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(bt)));
    render(<QualityTab sim={simWith} />);
    const row = (await screen.findByText("4,3%")).closest("tr")!;
    expect(row).toHaveTextContent("4,3%");
    expect(row).toHaveTextContent("80,0%");
    expect(row).toHaveTextContent("95,0%");
    expect(screen.getByText(/początki prognoz: 7, pominięte: 2/)).toBeInTheDocument();
    expect(screen.getByText(/obecnym prawie/)).toBeInTheDocument();
    expect(screen.getAllByText("założenie").length).toBeGreaterThan(0);
    expect(screen.getByText("vat.split").closest("tr")).toHaveClass("placeholder");
    expect(screen.getByText("cit.base").closest("tr")).not.toHaveClass("placeholder");
    expect(screen.getByRole("row", { name: /PIT.*1,0345/ })).toBeInTheDocument();
  });

  it("shows the message and a Polish error on 409", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ ...bt, mape: {}, coverage80: {}, coverage95: {}, message: "Za mało danych do backtestu" })));
    const { unmount } = render(<QualityTab sim={null} />);
    expect(await screen.findByText("Za mało danych do backtestu")).toBeInTheDocument();
    expect(screen.getByText(/Brak bieżącej symulacji/)).toBeInTheDocument();
    unmount();
    vi.stubGlobal("fetch", vi.fn(async () => json({ detail: "brak danych – uruchom odświeżenie" }, 409)));
    render(<QualityTab sim={null} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("brak danych");
  });
});

describe("ExportBar", () => {
  it("buttons are disabled without a result", () => {
    render(<ExportBar result={null} params={{}} getCharts={() => []} />);
    for (const name of ["Eksport CSV", "Eksport XLSX", "Wykres PNG", "Wykresy PDF"]) expect(screen.getByRole("button", { name })).toBeDisabled();
  });

  it("shows a Polish error on 413 and does not download", async () => {
    const dl = vi.spyOn(download, "downloadBlob").mockImplementation(() => {});
    vi.stubGlobal("fetch", vi.fn(async () => json({ detail: "Żądanie zbyt duże (maks. 1 MB)." }, 413)));
    render(<ExportBar result={sim} params={{ a: 1 }} getCharts={() => []} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Eksport CSV" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Żądanie zbyt duże");
    expect(dl).not.toHaveBeenCalled();
  });

  it("reports network errors in Polish and downloads on success", async () => {
    const dl = vi.spyOn(download, "downloadBlob").mockImplementation(() => {});
    const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError("fail")).mockResolvedValueOnce(new Response("a;b", { status: 200, headers: { "Content-Disposition": 'attachment; filename="symulacja-20261010.csv"' } }));
    vi.stubGlobal("fetch", fetchMock);
    render(<ExportBar result={sim} params={{ a: 1 }} getCharts={() => []} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Eksport CSV" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Brak połączenia z serwerem");
    await user.click(screen.getByRole("button", { name: "Eksport CSV" }));
    await waitFor(() => expect(dl).toHaveBeenCalledOnce());
    expect(dl.mock.calls[0][1]).toBe("symulacja-20261010.csv");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/export?format=csv");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("PNG export without a chart gives a Polish error", async () => {
    render(<ExportBar result={sim} params={{}} getCharts={() => []} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Wykres PNG" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Brak wykresu");
  });
});

describe("ScenarioBar", () => {
  const known = new Map([["vat_rate", { min: 0, max: 0.4 }]]);

  it("saves, loads and deletes a scenario", async () => {
    const onLoad = vi.fn();
    const user = userEvent.setup();
    render(<ScenarioBar params={{ vat_rate: 0.21 }} limits={known} onLoad={onLoad} />);
    expect(screen.getByRole("button", { name: "Zapisz scenariusz" })).toBeDisabled();
    await user.type(screen.getByLabelText("Nazwa scenariusza"), "Niższy VAT");
    await user.click(screen.getByRole("button", { name: "Zapisz scenariusz" }));
    expect(screen.getByRole("option", { name: "Niższy VAT" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Wczytaj" }));
    expect(onLoad).toHaveBeenCalledWith({ vat_rate: 0.21 });
    await user.click(screen.getByRole("button", { name: "Usuń" }));
    expect(screen.queryByRole("option", { name: "Niższy VAT" })).toBeNull();
  });

  it("shows the persistence warning instead of Zapisano when setItem fails", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });
    const user = userEvent.setup();
    render(<ScenarioBar params={{ vat_rate: 0.21 }} limits={known} onLoad={vi.fn()} />);
    await user.type(screen.getByLabelText("Nazwa scenariusza"), "A");
    await user.click(screen.getByRole("button", { name: "Zapisz scenariusz" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Nie udało się zapisać w pamięci przeglądarki");
    expect(screen.queryByText(/Zapisano/)).toBeNull();
    expect(screen.getByRole("option", { name: "A" })).toBeInTheDocument();
  });

  it("rejects an out-of-range import with a Polish message", async () => {
    render(<ScenarioBar params={{}} limits={known} onLoad={vi.fn()} />);
    const file = new File(['{"version":1,"scenarios":[{"name":"A","params":{"vat_rate":1e308}}]}'], "s.json", { type: "application/json" });
    await userEvent.setup().upload(screen.getByLabelText("Plik scenariuszy (JSON)"), file);
    expect(await screen.findByRole("alert")).toHaveTextContent("vat_rate");
  });

  it("loading a stored scenario drops unknown keys and clamps values", async () => {
    localStorage.setItem("symulator.scenarios.v1", JSON.stringify({ version: 1, scenarios: [{ name: "Stary", params: { vat_rate: 5, evil: 1 }, savedAt: "x" }] }));
    const onLoad = vi.fn();
    const user = userEvent.setup();
    render(<ScenarioBar params={{}} limits={known} onLoad={onLoad} />);
    await user.selectOptions(screen.getByLabelText("Zapisane scenariusze"), "Stary");
    await user.click(screen.getByRole("button", { name: "Wczytaj" }));
    expect(onLoad).toHaveBeenCalledWith({ vat_rate: 0.4 });
    expect(screen.getByRole("status")).toHaveTextContent("evil");
  });

  it("shows a Polish error in an alert for a bad import file", async () => {
    render(<ScenarioBar params={{}} limits={known} onLoad={vi.fn()} />);
    const file = new File([JSON.stringify({ version: 1, scenarios: [{ name: "A", params: { evil: 1 } }] })], "s.json", { type: "application/json" });
    await userEvent.setup().upload(screen.getByLabelText("Plik scenariuszy (JSON)"), file);
    expect(await screen.findByRole("alert")).toHaveTextContent("nieznany parametr");
  });

  it("imports a valid file", async () => {
    render(<ScenarioBar params={{}} limits={known} onLoad={vi.fn()} />);
    const file = new File([JSON.stringify({ version: 1, scenarios: [{ name: "Z pliku", params: { vat_rate: 0.2 } }] })], "s.json", { type: "application/json" });
    await userEvent.setup().upload(screen.getByLabelText("Plik scenariuszy (JSON)"), file);
    expect(await screen.findByRole("option", { name: "Z pliku" })).toBeInTheDocument();
  });
});

const known = new Map([["vat_rate", { min: 0, max: 0.4 }]]);

describe("CompareView", () => {
  it("simulates both scenarios and shows a differences table", async () => {
    saveScenario("Bazowy", { vat_rate: 0.23 });
    saveScenario("Niższy", { vat_rate: 0.21 });
    const other = { ...sim, taxes: { ...sim.taxes, vat: { ...sim.taxes.vat!, median: [300, 310] } } };
    let n = 0;
    vi.stubGlobal("fetch", vi.fn(async () => json(n++ === 0 ? sim : other)));
    const user = userEvent.setup();
    render(<CompareView limits={known} />);
    expect(screen.getByRole("button", { name: "Porównaj" })).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Scenariusz A"), "Bazowy");
    await user.selectOptions(screen.getByLabelText("Scenariusz B"), "Niższy");
    await user.click(screen.getByRole("button", { name: "Porównaj" }));
    const table = await screen.findByTestId("diff-table");
    const vat = within(table).getAllByRole("row").filter((r) => r.textContent?.startsWith("VAT2026"));
    expect(vat[0]).toHaveTextContent("-10,00");
    expect(table.textContent).not.toMatch(/NaN/);
  });

  it("sends only sanitized params to /simulate", async () => {
    localStorage.setItem(
      "symulator.scenarios.v1",
      JSON.stringify({ version: 1, scenarios: [{ name: "S1", params: { vat_rate: 9, evil: 1 }, savedAt: "x" }, { name: "S2", params: { vat_rate: 0.2 }, savedAt: "x" }] }),
    );
    const fetchMock = vi.fn(async () => json(sim));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<CompareView limits={known} />);
    await user.selectOptions(screen.getByLabelText("Scenariusz A"), "S1");
    await user.selectOptions(screen.getByLabelText("Scenariusz B"), "S2");
    await user.click(screen.getByRole("button", { name: "Porównaj" }));
    await screen.findByTestId("diff-table");
    const bodies = fetchMock.mock.calls.map((c) => JSON.parse((c as unknown as [string, RequestInit])[1].body as string).params);
    expect(bodies).toContainEqual({ vat_rate: 0.4 });
    expect(bodies.every((p) => !("evil" in p))).toBe(true);
    expect(screen.getByRole("status")).toHaveTextContent("evil");
  });

  it("asks for at least two scenarios", () => {
    render(<CompareView limits={known} />);
    expect(screen.getByText(/co najmniej dwa scenariusze/)).toBeInTheDocument();
  });
});

describe("App integration", () => {
  it("switches to the quality tab and loads the backtest only then", async () => {
    const params = [{ key: "vat_rate", label: "Stawka VAT", tax: "vat", unit: "ułamek", default: 0.23, min: 0, max: 0.4, step: 0.01, description: "x" }];
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        calls.push(url);
        if (url.endsWith("/parameters")) return json(params);
        if (url.endsWith("/refresh/status")) return json({ state: "done", errors: {}, updated_at: "2026-10-09T12:00:00Z" });
        if (url.endsWith("/backtest")) return json({ mape: { pit: 3 }, coverage80: { pit: 0.8 }, coverage95: { pit: 0.9 }, notes: [], message: null, n_origins: 4, n_skipped: 0 });
        if (url.endsWith("/history")) return json({ pit: [{ year: 2025, value: 100 }] });
        return json(sim);
      }),
    );
    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Eksport CSV" })).toBeEnabled());
    expect(calls.some((c) => c.endsWith("/backtest"))).toBe(false);
    await userEvent.setup().click(screen.getByRole("tab", { name: "Jakość modelu" }));
    expect(await screen.findByText("Backtest modelu")).toBeInTheDocument();
    expect(await screen.findByText("3,0%")).toBeInTheDocument();
  });
  it("renders CompareView only after the parameter schema has loaded", async () => {
    const params = [{ key: "vat_rate", label: "Stawka VAT", tax: "vat", unit: "ułamek", default: 0.23, min: 0, max: 0.4, step: 0.01, description: "x" }];
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.endsWith("/parameters")) {
          await gate;
          return json(params);
        }
        if (url.endsWith("/refresh/status")) return json({ state: "idle", errors: {}, updated_at: null });
        if (url.endsWith("/history")) return json({ pit: [{ year: 2025, value: 100 }] });
        return json(sim);
      }),
    );
    render(<App />);
    await userEvent.setup().click(screen.getByRole("tab", { name: "Porównanie scenariuszy" }));
    expect(screen.queryByRole("heading", { name: "Porównanie scenariuszy" })).not.toBeInTheDocument();
    release();
    expect(await screen.findByRole("heading", { name: "Porównanie scenariuszy" })).toBeInTheDocument();
  });
});
