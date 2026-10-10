import type { ApiErrorKind, ParamSpec, RefreshStatus, SimulateRequest, SimulationResult } from "./types";

export class ApiError extends Error {
  kind: ApiErrorKind;
  constructor(kind: ApiErrorKind, message: string) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
  }
}

const BASE = "/api";

async function detailOf(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    if (body && typeof body.detail === "string") return body.detail;
  } catch {
    /* brak JSON */
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, init);
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError("network", "Brak połączenia z serwerem");
  }
  if (res.ok) return (await res.json()) as T;
  if (res.status === 409) throw new ApiError("no-data", await detailOf(res, "brak danych – uruchom odświeżenie"));
  if (res.status === 422) throw new ApiError("invalid", await detailOf(res, "Nieprawidłowe parametry"));
  throw new ApiError("server", await detailOf(res, `Błąd serwera (${res.status})`));
}

export function getParameters(signal?: AbortSignal): Promise<ParamSpec[]> {
  return request<ParamSpec[]>("/parameters", { signal });
}

export function simulate(body: SimulateRequest, signal?: AbortSignal): Promise<SimulationResult> {
  return request<SimulationResult>("/simulate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
}

export async function startRefresh(): Promise<void> {
  await request<unknown>("/refresh", { method: "POST" });
}

export function getRefreshStatus(signal?: AbortSignal): Promise<RefreshStatus> {
  return request<RefreshStatus>("/refresh/status", { signal });
}
