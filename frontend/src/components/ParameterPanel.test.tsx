import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ParamSpec } from "../api/types";
import realParameters from "../testdata/parameters.json";
import { ParameterPanel } from "./ParameterPanel";

const schema: ParamSpec[] = [
  { key: "pit_rate_1", label: "Stawka PIT I", tax: "pit", unit: "ułamek", default: 0.12, min: 0, max: 0.5, step: 0.01, description: "Pierwszy próg PIT" },
  { key: "pit_free", label: "Kwota wolna", tax: "pit", unit: "zł", default: 30000, min: 0, max: 100000, step: 1000, description: "Kwota wolna od podatku" },
  { key: "cit_rate", label: "Stawka CIT", tax: "cit", unit: "ułamek", default: 0.19, min: 0, max: 0.5, step: 0.01, description: "Stawka CIT" },
  { key: "vat_rate", label: "Stawka VAT", tax: "vat", unit: "ułamek", default: 0.23, min: 0, max: 0.4, step: 0.01, description: "Stawka podstawowa VAT" },
];
const defaults = Object.fromEntries(schema.map((s) => [s.key, s.default]));

function setup(values: Record<string, number> = defaults) {
  const onChange = vi.fn();
  const onReset = vi.fn();
  render(<ParameterPanel schema={schema} values={values} onChange={onChange} onReset={onReset} />);
  return { onChange, onReset };
}

describe("ParameterPanel", () => {
  it("renders one section per tax from schema", () => {
    setup();
    expect(screen.getAllByRole("group")).toHaveLength(3);
    expect(screen.getByText("PIT – podatek dochodowy od osób fizycznych")).toBeInTheDocument();
    expect(screen.getByText("CIT – podatek dochodowy od osób prawnych")).toBeInTheDocument();
    expect(screen.getByText("VAT – podatek od towarów i usług")).toBeInTheDocument();
    expect(screen.getByLabelText("Stawka PIT I")).toBeInTheDocument();
  });

  it("marks parameter deviating from default", () => {
    setup({ ...defaults, cit_rate: 0.2 });
    expect(screen.getByTestId("deviation-cit_rate")).toBeInTheDocument();
    expect(screen.queryByTestId("deviation-vat_rate")).not.toBeInTheDocument();
  });

  it("reset restores default", async () => {
    const { onChange, onReset } = setup({ ...defaults, cit_rate: 0.2 });
    await userEvent.click(screen.getByRole("button", { name: "Przywróć Stawka CIT" }));
    expect(onChange).toHaveBeenCalledWith("cit_rate", 0.19);
    await userEvent.click(screen.getByRole("button", { name: "Przywróć wszystko" }));
    expect(onReset).toHaveBeenCalled();
  });

  it("calls onChange with a valid value (fraction shown as percent)", async () => {
    const { onChange } = setup();
    const input = screen.getByLabelText("Stawka CIT");
    await userEvent.clear(input);
    await userEvent.type(input, "21");
    expect(onChange).toHaveBeenLastCalledWith("cit_rate", 0.21);
  });

  it("rejects out-of-range input with a Polish message", async () => {
    const { onChange } = setup();
    const input = screen.getByLabelText("Stawka CIT");
    await userEvent.clear(input);
    await userEvent.type(input, "80");
    expect(onChange).not.toHaveBeenCalledWith("cit_rate", 0.8);
    expect(screen.getByRole("alert")).toHaveTextContent("Wartość poza zakresem");
    expect(input).toHaveAttribute("aria-invalid", "true");
  });

  it("shows description as tooltip and base value", () => {
    setup();
    const sec = screen.getByRole("group", { name: /VAT/ });
    expect(within(sec).getByText(/Stawka podstawowa VAT/)).toBeInTheDocument();
    expect(within(sec).getByText(/Baza: 23%/)).toBeInTheDocument();
  });

  it("per-parameter reset clears stale invalid text at default", async () => {
    const { onChange } = setup();
    const input = screen.getByLabelText("Stawka CIT");
    await userEvent.clear(input);
    await userEvent.type(input, "80");
    expect(screen.getByRole("alert")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Przywróć Stawka CIT" }));
    expect(input).toHaveValue("19");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalledWith("cit_rate", 0.8);
  });

  it("reset all clears stale invalid text at default", async () => {
    const { onChange, onReset } = setup();
    const input = screen.getByLabelText("Stawka CIT");
    await userEvent.clear(input);
    await userEvent.type(input, "80");
    await userEvent.click(screen.getByRole("button", { name: "Przywróć wszystko" }));
    expect(onReset).toHaveBeenCalled();
    expect(input).toHaveValue("19");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalledWith("cit_rate", 0.8);
  });
});

describe("ParameterPanel with the real backend contract", () => {
  it("renders a section and a field for every parameter of the backend schema", () => {
    const real = realParameters as ParamSpec[];
    const vals = Object.fromEntries(real.map((s) => [s.key, s.default]));
    render(<ParameterPanel schema={real} values={vals} onChange={vi.fn()} onReset={vi.fn()} />);
    expect(screen.getAllByRole("group")).toHaveLength(3);
    for (const s of real) expect(screen.getByLabelText(s.label, { exact: true })).toBeInTheDocument();
  });
});
