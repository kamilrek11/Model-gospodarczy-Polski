import type { DisabledModule } from "../api/types";

export function DisabledNotice({ modules }: { modules: DisabledModule[] }) {
  if (modules.length === 0) return null;
  return (
    <div className="notice warn" role="status">
      <strong>Część modułów jest wyłączona – wyniki są niepełne.</strong>
      <ul>
        {modules.map((m) => (
          <li key={m.module}>{m.message}</li>
        ))}
      </ul>
    </div>
  );
}
