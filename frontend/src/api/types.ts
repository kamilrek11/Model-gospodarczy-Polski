export type TaxKey = "pit" | "cit" | "vat";

export interface ParamSpec {
  key: string;
  label: string;
  tax: TaxKey;
  unit: string;
  default: number;
  min: number;
  max: number;
  step: number;
  description: string;
}

export interface Band {
  median: number[];
  p10: number[];
  p90: number[];
  p2_5: number[];
  p97_5: number[];
}

export interface BaselineBand {
  median: number[];
}

export interface MacroVar {
  median: number[];
  p10: number[];
  p90: number[];
  baseline: number[];
}

export interface CalibrationInfo {
  factor: number;
  years: number[];
  method: string;
}

export interface Assumption {
  key: string;
  value: number | null;
  status: string;
  note: string;
}

export interface DisabledModule {
  module: string;
  message: string;
}

export interface HistoryPoint {
  year: number;
  value: number;
}

/** GET /history – mld zł; podatek bez danych jest pominięty. */
export type HistoryData = Partial<Record<TaxKey, HistoryPoint[]>>;

export interface SimulationResult {
  years: number[];
  /** Wyłączony moduł nie ma wpisu. */
  taxes: Partial<Record<TaxKey, Band>>;
  baseline: Partial<Record<TaxKey | "total", BaselineBand>>;
  total: Band;
  macro: Record<string, MacroVar>;
  calibration: Partial<Record<TaxKey, CalibrationInfo>>;
  assumptions: Assumption[];
  disabled_modules: DisabledModule[];
  model_version?: string;
  data_updated_at?: string | null;
}

export interface SimulateRequest {
  params: Record<string, number>;
  horizon: number;
  n_paths: number;
  seed?: number;
}

export type ApiErrorKind = "no-data" | "invalid" | "network" | "server";

export interface RefreshStatus {
  state: "idle" | "running" | "done" | "failed";
  errors: Record<string, string>;
  updated_at: string | null;
}
