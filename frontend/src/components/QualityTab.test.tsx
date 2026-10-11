import { render, screen, within } from "@testing-library/react";
import type { SimulationResult } from "../api/types";
import realSimulation from "../testdata/simulation.json";
import { QualityTab } from "./QualityTab";

// simulation.json = real backend /simulate output on a SYNTHETIC tmp store (backend/tests/frontend_fixtures.py).
const sim = realSimulation as SimulationResult;
const json = (b: unknown) => new Response(JSON.stringify(b), { status: 200 });
const bt = { mape: {}, coverage80: {}, coverage95: {}, notes: [], message: "brak", n_origins: 0, n_skipped: 0 };

afterEach(() => vi.unstubAllGlobals());

describe("QualityTab with real backend assumptions", () => {
  it("renders scalar, dict and matrix assumption values without NaN", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(bt)));
    const { container } = render(<QualityTab sim={sim} />);
    await screen.findByText("brak");
    expect(container.textContent).not.toMatch(/NaN/);

    const item = (key: string) => screen.getByText(key, { selector: "code" }).closest("li")!;
    // scalar
    expect(item("VAT_GAP")).toHaveTextContent("= 0,109");
    // dict -> compact key: value list
    const shares = item("VAT_CONSUMPTION_SHARES");
    expect(shares).toHaveTextContent("standard: 0,55");
    expect(shares).toHaveTextContent("zero: 0,18");
    // matrix -> summary + table in <details>
    const dist = item("PIT_INCOME_DIST_DEFAULT");
    expect(dist).toHaveTextContent("14 grup × 2 kolumny");
    const table = within(dist).getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(14);
    expect(table).toHaveTextContent("520 000");
  });

  it("shows the from_data status for the constant computed from stored series", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(bt)));
    render(<QualityTab sim={sim} />);
    await screen.findByText("brak");
    const row = screen.getByText("CONSUMPTION_GDP_SHARE", { selector: "code" }).closest("li")!;
    expect(row).toHaveTextContent("from_data");
    expect(row).toHaveTextContent("= 0,57");
  });
});
