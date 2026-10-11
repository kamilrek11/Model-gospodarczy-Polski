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

    const item = (key: string) => screen.getByText(key, { selector: "code" }).closest("tr")!;
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
    const row = screen.getByText("CONSUMPTION_GDP_SHARE", { selector: "code" }).closest("tr")!;
    expect(row).toHaveTextContent("z danych");
    expect(row).not.toHaveTextContent("from_data");
    const a = sim.assumptions.find((x) => x.key === "CONSUMPTION_GDP_SHARE")!;
    expect(a.status).toBe("from_data");
    expect(a.value).toBeCloseTo(0.57, 6); // synthetic gdp_nominal = consumption / 0.57
    expect(row).toHaveTextContent("= 0,57");
    expect(row).toHaveTextContent(`0,570 w ${a.year} r.`);
  });
});

describe("QualityTab constant provenance table", () => {
  const rows = [
    { key: "SRC", value: 0.1, status: "sourced", note: "n1", source: "MF CIT 2021", year: 2021, url: "https://example.org/doc.pdf", low: 0.05, high: 0.12 },
    { key: "ASM", value: 2, status: "assumption", note: "brak źródła", source: "", year: null, url: "", low: null, high: null },
    { key: "BAD", value: 3, status: "sourced", note: "n", source: "Zły", year: 2020, url: "javascript:alert(1)", low: 1, high: 4 },
    { key: "DATA", value: 0.57, status: "from_data", note: "n", source: "", year: 2024, url: "", low: null, high: null },
    { key: "structure.x", value: null, status: "model-structure", note: "metoda" },
  ];
  const simP = { ...sim, assumptions: rows } as SimulationResult;

  it("has Status/Źródło/Zakres columns and Polish status labels", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(bt)));
    const { container } = render(<QualityTab sim={simP} />);
    await screen.findByText("brak");
    const table = screen.getByRole("table", { name: /Stałe i założenia modelu/ });
    for (const h of ["Status", "Źródło", "Zakres"]) expect(within(table).getByRole("columnheader", { name: h })).toBeInTheDocument();
    expect(within(table).getAllByText("założenie").length).toBe(1);
    expect(within(table).getAllByText("ze źródła").length).toBe(2);
    expect(within(table).getByText("z danych")).toBeInTheDocument();
    expect(within(table).getByText("struktura modelu")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/PLACEHOLDER/);
    const src = screen.getByText("SRC", { selector: "code" }).closest("tr")!;
    expect(src).toHaveTextContent("MF CIT 2021");
    expect(src).toHaveTextContent("2021");
    expect(src).toHaveTextContent("0,05–0,12");
  });

  it("links the source only for http(s) urls and highlights assumptions", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(bt)));
    render(<QualityTab sim={simP} />);
    await screen.findByText("brak");
    const link = within(screen.getByText("SRC", { selector: "code" }).closest("tr")!).getByRole("link", { name: /MF CIT 2021/ });
    expect(link).toHaveAttribute("href", "https://example.org/doc.pdf");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(within(screen.getByText("BAD", { selector: "code" }).closest("tr")!).queryByRole("link")).toBeNull();
    expect(screen.getByText("ASM", { selector: "code" }).closest("tr")).toHaveClass("placeholder");
    expect(screen.getByText("SRC", { selector: "code" }).closest("tr")).not.toHaveClass("placeholder");
    expect(screen.getByRole("note")).toHaveTextContent("1 z założeń");
  });

  it("shows no warning when every constant has a source", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(bt)));
    render(<QualityTab sim={{ ...sim, assumptions: rows.filter((r) => r.key !== "ASM") } as SimulationResult} />);
    await screen.findByText("brak");
    expect(screen.queryByRole("note")).toBeNull();
  });

  it("treats a legacy PLACEHOLDER status from cached results as an assumption", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(bt)));
    const old = [{ key: "OLD", value: 1, status: "PLACEHOLDER-UNVERIFIED", note: "n", source: "", year: null, url: "", low: null, high: null }];
    const { container } = render(<QualityTab sim={{ ...sim, assumptions: old } as SimulationResult} />);
    await screen.findByText("brak");
    const row = screen.getByText("OLD", { selector: "code" }).closest("tr")!;
    expect(row).toHaveClass("placeholder");
    expect(row).toHaveTextContent("założenie");
    expect(screen.getByRole("note")).toHaveTextContent("1 z założeń");
    expect(container.textContent).not.toMatch(/PLACEHOLDER/);
  });
});
