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

export interface SimulationResult {
  years: number[];
  taxes: Record<TaxKey, Band>;
  baseline: Record<string, unknown>;
  total: Band;
  macro: Record<string, unknown>;
  calibration: unknown;
  assumptions: unknown;
  disabled_modules: unknown;
  model_version: string;
  data_updated_at: string | null;
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
