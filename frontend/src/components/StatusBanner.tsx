import type { ApiError } from "../api/client";
import type { RefreshStatus } from "../api/types";
import { fmtDate } from "../format";
import { RefreshButton } from "./RefreshButton";

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
  const sourceError = error !== null && error.kind !== "no-data" && error.kind !== "invalid";
  if (!failed && !running && !sourceError) return null;

  const names = failed ? Object.keys(status.errors) : [];
  const last = updatedAt ?? status?.updated_at ?? null;

  return (
    <div className={`notice ${running && !failed ? "info" : "error-banner"}`} role={running && !failed ? "status" : "alert"}>
      <div>
        {running && !failed && <strong>Trwa odświeżanie danych…</strong>}
        {failed && (
          <strong>
            Nie udało się odświeżyć danych{names.length > 0 ? `: ${names.join(", ")}` : ""}.
          </strong>
        )}
        {sourceError && !failed && <strong>{error.message}</strong>}
        {(failed || sourceError) && (
          <span className="last-good">
            {" "}
            {last ? `Ostatnie poprawne dane z ${fmtDate(last)}.` : "Brak poprawnych danych."}
          </span>
        )}
        {failed &&
          names.length > 0 &&
          (
            <ul>
              {names.map((n) => (
                <li key={n}>
                  {n}: {status.errors[n]}
                </li>
              ))}
            </ul>
          )}
      </div>
      <RefreshButton status={status} onRefresh={onRefresh} />
    </div>
  );
}
