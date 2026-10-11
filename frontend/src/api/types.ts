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

/** Wartość stałej modelu: liczba, słownik (np. VAT_CONSUMPTION_SHARES) lub macierz (np. PIT_INCOME_DIST_DEFAULT). */
export type AssumptionValue = number | number[][] | Record<string, number> | null;

export interface Assumption {
  key: string;
  value: AssumptionValue;
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
export type HistoryData = Partial<Record<TaxKey, HistoryPoint[]>> & {
  /** true: dane zasiane syntetycznie (nie GUS/MF). */
  synthetic?: boolean;
};

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
  /** true: wynik policzony na danych syntetycznych (meta synthetic == "1"). */
  synthetic?: boolean;
}

export interface SimulateRequest {
  params: Record<string, number>;
  horizon: number;
  n_paths: number;
  seed?: number;
}

export type ApiErrorKind = "no-data" | "invalid" | "network" | "server" | "disabled";

export interface RefreshStatus {
  state: "idle" | "running" | "done" | "failed";
  errors: Record<string, string>;
  updated_at: string | null;
  synthetic?: boolean;
  /** Ostrzeżenia źródeł z ostatniego odświeżenia (np. nieobsłużony rok MF) – nie są błędem. */
  warnings?: string[];
  /** Odświeżanie wyłączone w tej instancji (REFRESH_DISABLED=1). */
  disabled?: boolean;
}

/** GET /backtest – MAPE w %, pokrycie jako ułamek (0-1), klucze = podatki. */
export interface BacktestResult {
  mape: Partial<Record<TaxKey, number>>;
  coverage80: Partial<Record<TaxKey, number>>;
  coverage95: Partial<Record<TaxKey, number>>;
  notes: string[];
  message: string | null;
  n_origins: number;
  n_skipped: number;
}

export interface ExportRequest {
  params: Record<string, number>;
  result: SimulationResult;
}
