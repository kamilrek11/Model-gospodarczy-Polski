import type { RefreshStatus } from "../api/types";

export const MSG_REFRESH_DISABLED = "Odświeżanie wyłączone w tej instancji.";

export function RefreshButton({ status, onRefresh }: { status: RefreshStatus | null; onRefresh: () => void }) {
  const running = status?.state === "running";
  const disabled = status?.disabled === true;
  return (
    <button type="button" className="primary" disabled={running || disabled} title={disabled ? MSG_REFRESH_DISABLED : undefined} onClick={onRefresh}>
      {running ? "Odświeżanie…" : "Odśwież dane"}
    </button>
  );
}
