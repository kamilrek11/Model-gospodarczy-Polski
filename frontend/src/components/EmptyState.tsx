import type { RefreshStatus } from "../api/types";
import { MSG_REFRESH_DISABLED, RefreshButton } from "./RefreshButton";

export function EmptyState({ status, onRefresh }: { status: RefreshStatus | null; onRefresh: () => void }) {
  return (
    <div className="empty-state">
      <h2>Brak danych źródłowych</h2>
      <p>
        Symulator nie ma jeszcze pobranych danych (GUS, NBP, Ministerstwo Finansów), dlatego nie może policzyć prognozy. Pobranie
        danych może potrwać kilkadziesiąt sekund.
      </p>
      <RefreshButton status={status} onRefresh={onRefresh} />
      {status?.state === "running" && <p role="status">Trwa pobieranie danych…</p>}
      {status?.disabled && <p role="alert">{MSG_REFRESH_DISABLED}</p>}
      {status?.state === "failed" && !status.disabled && (
        <p role="alert">
          Odświeżenie nie powiodło się{Object.keys(status.errors).length > 0 ? `: ${Object.keys(status.errors).join(", ")}` : ""}. Spróbuj ponownie.
        </p>
      )}
    </div>
  );
}
