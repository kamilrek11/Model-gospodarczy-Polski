import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { RefreshStatus } from "./api/types";
import { CompareView } from "./components/CompareView";
import { resetScenarioStore, saveScenario } from "./scenarios/store";
import { SIMULATION_SEED } from "./state/useSimulation";
import { sim } from "./testFixtures";

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status });
const params = [{ key: "vat_rate", label: "Stawka VAT", tax: "vat", unit: "ułamek", default: 0.23, min: 0, max: 0.4, step: 0.01, description: "x" }];
const SYNTH = "DANE SYNTETYCZNE – nie są to dane GUS/MF";

interface Opts {
  synthetic?: boolean;
  status?: Partial<RefreshStatus> & { synthetic?: boolean };
  noData?: boolean;
}

function stubApi({ synthetic = false, status = {}, noData = false }: Opts = {}) {
  const simBodies: Record<string, unknown>[] = [];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/parameters")) return json(params);
    if (url.endsWith("/refresh/status")) return json({ state: "idle", errors: {}, updated_at: "2026-10-09T12:00:00Z", synthetic, ...status });
    if (url.endsWith("/refresh")) return json({ state: "running" }, 202);
    if (noData) return json({ detail: "brak danych – uruchom odświeżenie" }, 409);
    if (url.endsWith("/history")) return json({ pit: [{ year: 2025, value: 100 }], synthetic });
    if (url.endsWith("/simulate")) {
      simBodies.push(JSON.parse(init!.body as string));
      return json({ ...sim, synthetic, model_version: "abcdef123456" });
    }
    return json({});
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, simBodies };
}

beforeEach(() => {
  localStorage.clear();
  resetScenarioStore();
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("I-6: fixed simulation seed", () => {
  it("every main-view simulate call carries SIMULATION_SEED", async () => {
    const { simBodies } = stubApi();
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(simBodies).toHaveLength(1));
    const input = screen.getByLabelText("Stawka VAT", { selector: "input[type=text]" });
    await user.clear(input);
    await user.type(input, "25{Enter}");
    await waitFor(() => expect(simBodies.length).toBeGreaterThanOrEqual(2));
    expect(simBodies.map((b) => b.seed)).toEqual(simBodies.map(() => SIMULATION_SEED));
    expect(SIMULATION_SEED).toBe(1);
  });

  it("CompareView uses the same shared seed", async () => {
    saveScenario("A", { vat_rate: 0.23 });
    saveScenario("B", { vat_rate: 0.25 });
    const { simBodies } = stubApi();
    const user = userEvent.setup();
    render(<CompareView limits={new Map([["vat_rate", { min: 0, max: 0.4 }]])} />);
    await user.selectOptions(screen.getByLabelText("Scenariusz A"), "A");
    await user.selectOptions(screen.getByLabelText("Scenariusz B"), "B");
    await user.click(screen.getByRole("button", { name: "Porównaj" }));
    await screen.findByTestId("diff-table");
    expect(simBodies.map((b) => b.seed)).toEqual([SIMULATION_SEED, SIMULATION_SEED]);
  });
});

describe("C-1: synthetic data banner", () => {
  it("shows a persistent, non-dismissable status banner when the data is synthetic", async () => {
    stubApi({ synthetic: true });
    render(<App />);
    const banner = await screen.findByText(SYNTH);
    const region = banner.closest("[role=status]")!;
    expect(region).toBeInTheDocument();
    expect(within(region as HTMLElement).queryByRole("button")).not.toBeInTheDocument();
    // at the top of the app, before the main layout
    const app = document.querySelector(".app")!;
    expect(app.firstElementChild).toBe(region);
  });

  it("shows the banner from /refresh/status even when there is no simulation yet", async () => {
    stubApi({ synthetic: true, noData: true });
    render(<App />);
    expect(await screen.findByText(SYNTH)).toBeInTheDocument();
  });

  it("no banner for real data", async () => {
    stubApi({ synthetic: false });
    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Eksport CSV" })).toBeEnabled());
    expect(screen.queryByText(SYNTH)).not.toBeInTheDocument();
  });
});

describe("I-2: top bar shows refresh button, data date and model version", () => {
  const topbar = () => document.querySelector("header.topbar") as HTMLElement;

  it("in the normal state", async () => {
    const { fetchMock } = stubApi();
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(within(topbar()).getByText(/Dane z: 09\.10\.2026/)).toBeInTheDocument());
    await waitFor(() => expect(within(topbar()).getByText(/model abcdef1\b/)).toBeInTheDocument());
    const btn = within(topbar()).getByRole("button", { name: "Odśwież dane" });
    expect(btn).toBeEnabled();
    await user.click(btn);
    await waitFor(() => expect(fetchMock.mock.calls.some(([u, i]) => u === "/api/refresh" && (i as RequestInit | undefined)?.method === "POST")).toBe(true));
    expect(within(topbar()).getByRole("button", { name: "Odświeżanie…" })).toBeDisabled();
  });

  it("reflects a failed refresh", async () => {
    stubApi({ status: { state: "failed", errors: { gus_bdl: "x" } } });
    render(<App />);
    expect(await within(topbar()).findByText(/odświeżenie nieudane/i)).toBeInTheDocument();
    expect(within(topbar()).getByRole("button", { name: "Odśwież dane" })).toBeEnabled();
  });

  it("shows 'brak' when no data date is known", async () => {
    stubApi({ noData: true, status: { updated_at: null } });
    render(<App />);
    expect(await within(topbar()).findByText(/Dane z: brak/)).toBeInTheDocument();
  });
});
