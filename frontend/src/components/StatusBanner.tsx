import type { ApiError } from "../api/client";
import type { RefreshStatus } from "../api/types";
import { fmtDate } from "../format";
import { MSG_REFRESH_DISABLED, RefreshButton } from "./RefreshButton";

interface Props {
  /** Błąd ostatniego zapytania o symulację / historię (inny niż brak danych). */
  error: ApiError | null;
  status: RefreshStatus | null;
  /** Data ostatnich poprawnych danych (updated_at). */
  updatedAt: string | null;
  onRefresh: () => void;
}

export function StatusBanner({ error, status, updatedAt, onRefresh }: Props) {
  const failed = status?.state === "failed";
  const running = status?.state === "running";
  const disabled = failed && status.disabled === true;
  const sourceError = error !== null && error.kind !== "no-data" && error.kind !== "invalid";
  const warnings = !running ? (status?.warnings ?? []) : [];
  if (!failed && !running && !sourceError && warnings.length === 0) return null;

  const names = failed && !disabled ? Object.keys(status.errors) : [];
  const last = updatedAt ?? status?.updated_at ?? null;
  const alarm = failed || sourceError;

  return (
    <div className={`notice ${alarm ? "error-banner" : "info"}`} role={alarm ? "alert" : "status"}>
      <div>
        {running && !failed && <strong>Trwa odświeżanie danych…</strong>}
        {disabled && <strong>{MSG_REFRESH_DISABLED}</strong>}
        {failed && !disabled && (
          <strong>
            Nie udało się odświeżyć danych{names.length > 0 ? `: ${names.join(", ")}` : ""}.
          </strong>
        )}
        {sourceError && !failed && <strong>{error.message}</strong>}
        {alarm && (
          <span className="last-good">
            {" "}
            {last ? `Ostatnie poprawne dane z ${fmtDate(last)}.` : "Brak poprawnych danych."}
          </span>
        )}
        {names.length > 0 && (
          <ul>
            {names.map((n) => (
              <li key={n}>
                {n}: {status!.errors[n]}
              </li>
            ))}
          </ul>
        )}
        {warnings.length > 0 && (
          <>
            {!alarm && <strong>Uwagi do danych z ostatniego odświeżenia:</strong>}
            {alarm && <span> Uwagi do danych z ostatniego odświeżenia:</span>}
            <ul>
              {warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </>
        )}
      </div>
      <RefreshButton status={status} onRefresh={onRefresh} />
    </div>
  );
}
