import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { compare } from "./compare";
import { PERSIST_WARNING, sanitizeParams, MAX_NAME_LENGTH, MAX_SCENARIOS, deleteScenario, exportScenarios, importScenarios, listScenarios, resetScenarioStore, saveScenario } from "./store";
import { sim } from "../testFixtures";

const KNOWN = new Set(["vat_rate", "cit_rate"]);
const doc = (scenarios: unknown, version: unknown = 1) => JSON.stringify({ version, scenarios });
const entry = (name: string, params: Record<string, unknown> = { vat_rate: 0.23 }) => ({ name, params, savedAt: "2026-10-10T10:00:00Z" });

beforeEach(() => {
  localStorage.clear();
  resetScenarioStore();
});
afterEach(() => vi.restoreAllMocks());

describe("scenario store", () => {
  it("save and list roundtrip", () => {
    expect(saveScenario("Niższy VAT", { vat_rate: 0.21 })).toEqual({ ok: true });
    const list = listScenarios();
    expect(list).toHaveLength(1);
    expect(list[0]).toMatchObject({ name: "Niższy VAT", params: { vat_rate: 0.21 } });
    expect(typeof list[0].savedAt).toBe("string");
    deleteScenario("Niższy VAT");
    expect(listScenarios()).toEqual([]);
  });

  it("saving under an existing name overwrites it", () => {
    saveScenario("A", { vat_rate: 0.2 });
    saveScenario("A", { vat_rate: 0.25 });
    expect(listScenarios()).toHaveLength(1);
    expect(listScenarios()[0].params.vat_rate).toBe(0.25);
  });

  it("rejects empty and over-long names on save", () => {
    expect(saveScenario("   ", {})).toMatchObject({ ok: false });
    const r = saveScenario("x".repeat(MAX_NAME_LENGTH + 1), {});
    expect(r).toMatchObject({ ok: false });
    expect(listScenarios()).toEqual([]);
  });

  it("localStorage failure does not throw and falls back to memory", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });
    expect(() => saveScenario("A", { vat_rate: 0.2 })).not.toThrow();
    expect(listScenarios().map((s) => s.name)).toEqual(["A"]);
    expect(() => exportScenarios()).not.toThrow();
    expect(importScenarios(doc([entry("B")]), KNOWN)).toMatchObject({ ok: true, warning: PERSIST_WARNING });
    expect(listScenarios().map((s) => s.name).sort()).toEqual(["A", "B"]);
    expect(() => deleteScenario("A")).not.toThrow();
  });

  it("tolerates corrupted stored JSON", () => {
    localStorage.setItem("symulator.scenarios.v1", "{not json");
    expect(listScenarios()).toEqual([]);
    localStorage.setItem("symulator.scenarios.v1", JSON.stringify({ version: 1, scenarios: [{ name: 5 }, null, entry("ok")] }));
    expect(listScenarios().map((s) => s.name)).toEqual(["ok"]);
    expect(saveScenario("nowy", {})).toEqual({ ok: true });
  });
});

describe("persist failures with a working getItem", () => {
  const quota = () =>
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });

  it("keeps the saved scenario listed and returns a warning", () => {
    quota();
    const r = saveScenario("A", { vat_rate: 0.2 });
    expect(r).toEqual({ ok: true, warning: PERSIST_WARNING });
    expect(listScenarios().map((s) => s.name)).toEqual(["A"]);
    expect(saveScenario("B", {})).toMatchObject({ warning: PERSIST_WARNING });
    expect(listScenarios().map((s) => s.name)).toEqual(["A", "B"]);
  });

  it("delete and import also warn and stay consistent", () => {
    saveScenario("A", {});
    saveScenario("B", {});
    quota();
    expect(deleteScenario("A")).toMatchObject({ ok: true, warning: PERSIST_WARNING });
    expect(listScenarios().map((s) => s.name)).toEqual(["B"]);
    expect(importScenarios(doc([entry("C")]), KNOWN)).toMatchObject({ ok: true, warning: PERSIST_WARNING });
    expect(listScenarios().map((s) => s.name)).toEqual(["B", "C"]);
  });

  it("returns to normal persistence after a successful write", () => {
    const spy = quota();
    saveScenario("A", {});
    spy.mockRestore();
    expect(saveScenario("B", {})).toEqual({ ok: true });
    expect(listScenarios().map((s) => s.name)).toEqual(["A", "B"]);
  });
});

describe("parameter ranges", () => {
  const LIMITS = new Map([["vat_rate", { min: 0, max: 0.4 }]]);

  it("import with 1e308 is rejected naming the key", () => {
    const r = importScenarios('{"version":1,"scenarios":[{"name":"A","params":{"vat_rate":1e308}}]}', KNOWN, LIMITS);
    expect(r).toMatchObject({ ok: false });
    expect((r as { error: string }).error).toContain("vat_rate");
    expect(listScenarios()).toEqual([]);
  });

  it("sanitizeParams drops unknown keys and clamps out-of-range values with notes", () => {
    const { params, notes } = sanitizeParams({ vat_rate: 9, evil: 1, x: NaN }, LIMITS);
    expect(params).toEqual({ vat_rate: 0.4 });
    expect(notes).toHaveLength(3);
    expect(notes.join(" ")).toContain("evil");
  });
});

describe("importScenarios", () => {
  it("roundtrips export -> import", () => {
    saveScenario("A", { vat_rate: 0.2 });
    const json = exportScenarios();
    expect(JSON.parse(json).version).toBe(1);
    deleteScenario("A");
    expect(importScenarios(json, KNOWN)).toEqual({ ok: true });
    expect(listScenarios()[0]).toMatchObject({ name: "A", params: { vat_rate: 0.2 } });
  });

  it("import rejects older schema version", () => {
    const r = importScenarios(doc([entry("A")], 0), KNOWN);
    expect(r).toMatchObject({ ok: false });
    expect((r as { error: string }).error).toMatch(/wersj/i);
    expect(importScenarios(doc([entry("A")], 2), KNOWN)).toMatchObject({ ok: false });
    expect(importScenarios(JSON.stringify({ scenarios: [] }), KNOWN)).toMatchObject({ ok: false });
    expect(listScenarios()).toEqual([]);
  });

  it("import rejects unknown parameter keys", () => {
    const r = importScenarios(doc([entry("A", { vat_rate: 0.2, evil: 1 })]), KNOWN);
    expect(r).toMatchObject({ ok: false });
    expect((r as { error: string }).error).toContain("evil");
    expect(listScenarios()).toEqual([]);
  });

  it("rejects invalid JSON, non-array, non-finite and non-numeric values without throwing", () => {
    expect(importScenarios("{oops", KNOWN)).toMatchObject({ ok: false });
    expect(importScenarios("null", KNOWN)).toMatchObject({ ok: false });
    expect(importScenarios(doc({ a: 1 }), KNOWN)).toMatchObject({ ok: false });
    expect(importScenarios(doc([entry("A", { vat_rate: "0.2" })]), KNOWN)).toMatchObject({ ok: false });
    expect(importScenarios(doc([entry("A", { vat_rate: null })]), KNOWN)).toMatchObject({ ok: false });
    expect(importScenarios('{"version":1,"scenarios":[{"name":"A","params":{"vat_rate":1e999}}]}', KNOWN)).toMatchObject({ ok: false });
    expect(importScenarios(doc([entry("A", [] as never)]), KNOWN)).toMatchObject({ ok: false });
    expect(importScenarios(doc([null]), KNOWN)).toMatchObject({ ok: false });
  });

  it("rejects empty, duplicate and over-long names", () => {
    expect(importScenarios(doc([entry("")]), KNOWN)).toMatchObject({ ok: false });
    expect(importScenarios(doc([entry("A"), entry("A")]), KNOWN)).toMatchObject({ ok: false });
    expect(importScenarios(doc([entry("y".repeat(MAX_NAME_LENGTH + 1))]), KNOWN)).toMatchObject({ ok: false });
    expect(listScenarios()).toEqual([]);
  });

  it("rejects too many scenarios and oversize input", () => {
    const many = Array.from({ length: MAX_SCENARIOS + 1 }, (_, i) => entry(`s${i}`));
    expect(importScenarios(doc(many), KNOWN)).toMatchObject({ ok: false });
    const huge = doc([entry("A")]) + " ".repeat(1024 * 1024);
    const r = importScenarios(huge, KNOWN);
    expect(r).toMatchObject({ ok: false });
    expect((r as { error: string }).error).toMatch(/1 MB/);
  });

  it("rejects __proto__ keys even without a known-key registry", () => {
    const json = '{"version":1,"scenarios":[{"name":"A","params":{"__proto__":1}}]}';
    expect(importScenarios(json)).toMatchObject({ ok: false });
  });
});

describe("compare", () => {
  const b = { ...sim, taxes: { ...sim.taxes, pit: { ...sim.taxes.pit!, median: [110, 121] } } };

  it("compare returns per-tax differences", () => {
    const rows = compare(sim, b);
    const pit2026 = rows.find((r) => r.tax === "pit" && r.year === 2026)!;
    expect(pit2026).toMatchObject({ a: 100, b: 110, diff: 10 });
    expect(pit2026.pct).toBeCloseTo(10, 5);
    const pit2027 = rows.find((r) => r.tax === "pit" && r.year === 2027)!;
    expect(pit2027.diff).toBeCloseTo(10.5);
    expect(rows.find((r) => r.tax === "vat" && r.year === 2026)).toMatchObject({ diff: 0, pct: 0 });
    expect(rows).toHaveLength(6);
  });

  it("handles different year sets and missing taxes without NaN", () => {
    const other = { years: [2027, 2028], taxes: { pit: { ...sim.taxes.pit!, median: [105, 120] } } };
    const rows = compare(sim, other);
    expect(JSON.stringify(rows)).not.toMatch(/NaN|Infinity/);
    expect(rows.find((r) => r.tax === "pit" && r.year === 2026)).toMatchObject({ a: 100, b: null, diff: null, pct: null });
    expect(rows.find((r) => r.tax === "pit" && r.year === 2028)).toMatchObject({ a: null, b: 120, diff: null, pct: null });
    expect(rows.find((r) => r.tax === "pit" && r.year === 2027)).toMatchObject({ a: 110.5, b: 105, diff: -5.5 });
    expect(rows.find((r) => r.tax === "cit" && r.year === 2027)).toMatchObject({ a: 66, b: null, diff: null });
  });

  it("gives null percent when the base is zero", () => {
    const z = { years: [2026], taxes: { pit: { ...sim.taxes.pit!, median: [0] } } };
    const r = compare(z, sim).find((x) => x.tax === "pit")!;
    expect(r.diff).toBe(100);
    expect(r.pct).toBeNull();
  });
});
