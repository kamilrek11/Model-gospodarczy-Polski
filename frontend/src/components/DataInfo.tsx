import type { RefreshStatus } from "../api/types";
import { fmtDate } from "../format";
import { RefreshButton } from "./RefreshButton";

interface Props {
  updatedAt: string | null;
  modelVersion: string | null;
  status: RefreshStatus | null;
  onRefresh: () => void;
}

/** Pasek górny: data danych, wersja modelu i przycisk odświeżenia (zawsze widoczne). */
export function DataInfo({ updatedAt, modelVersion, status, onRefresh }: Props) {
  return (
    <div className="data-info">
      <span>Dane z: {updatedAt ? fmtDate(updatedAt) : "brak"}</span>
      {modelVersion && <span title={`Wersja modelu ${modelVersion}`}>model {modelVersion.slice(0, 7)}</span>}
      {status?.disabled ? (
        <span className="refresh-failed">odświeżanie wyłączone</span>
      ) : (
        status?.state === "failed" && <span className="refresh-failed">odświeżenie nieudane</span>
      )}
      <RefreshButton status={status} onRefresh={onRefresh} />
    </div>
  );
}
