import type { RefreshStatus } from "../api/types";

export function RefreshButton({ status, onRefresh }: { status: RefreshStatus | null; onRefresh: () => void }) {
  const running = status?.state === "running";
  return (
    <button type="button" className="primary" disabled={running} onClick={onRefresh}>
      {running ? "Odświeżanie…" : "Odśwież dane"}
    </button>
  );
}
