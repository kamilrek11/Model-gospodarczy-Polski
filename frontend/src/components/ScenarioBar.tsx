import { useId, useRef, useState } from "react";
import { downloadBlob } from "../export/download";
import { deleteScenario, exportScenarios, importScenarios, listScenarios, saveScenario, MAX_NAME_LENGTH, type Scenario } from "../scenarios/store";

interface Props {
  params: Record<string, number>;
  knownKeys: ReadonlySet<string>;
  onLoad: (params: Record<string, number>) => void;
}

export function ScenarioBar({ params, knownKeys, onLoad }: Props) {
  const id = useId();
  const [scenarios, setScenarios] = useState<Scenario[]>(listScenarios);
  const [name, setName] = useState("");
  const [selected, setSelected] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = () => setScenarios(listScenarios());
  const fail = (msg: string) => {
    setInfo(null);
    setError(msg);
  };

  const onSave = () => {
    const r = saveScenario(name, params);
    if (!r.ok) return fail(r.error);
    setError(null);
    setInfo(`Zapisano scenariusz „${name.trim()}”.`);
    setSelected(name.trim());
    setName("");
    refresh();
  };

  const onDelete = () => {
    deleteScenario(selected);
    setError(null);
    setInfo(`Usunięto scenariusz „${selected}”.`);
    setSelected("");
    refresh();
  };

  const onLoadClick = () => {
    const s = scenarios.find((x) => x.name === selected);
    if (!s) return;
    setError(null);
    setInfo(`Wczytano scenariusz „${s.name}”.`);
    onLoad(s.params);
  };

  const onExport = () => {
    downloadBlob(new Blob([exportScenarios()], { type: "application/json" }), "scenariusze.json");
  };

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    let text: string;
    try {
      text = await file.text();
    } catch {
      return fail("Nie udało się odczytać pliku.");
    }
    const r = importScenarios(text, knownKeys);
    if (!r.ok) return fail(r.error);
    setError(null);
    setInfo("Zaimportowano scenariusze.");
    refresh();
  };

  return (
    <section className="scenario-bar" aria-label="Scenariusze">
      <h2>Scenariusze</h2>
      <div className="controls">
        <label htmlFor={`${id}-name`} className="sr-only">
          Nazwa scenariusza
        </label>
        <input id={`${id}-name`} type="text" value={name} maxLength={MAX_NAME_LENGTH} placeholder="Nazwa scenariusza" onChange={(e) => setName(e.target.value)} />
        <button type="button" onClick={onSave} disabled={!name.trim()}>
          Zapisz scenariusz
        </button>
      </div>
      <div className="controls">
        <label htmlFor={`${id}-pick`} className="sr-only">
          Zapisane scenariusze
        </label>
        <select id={`${id}-pick`} value={selected} onChange={(e) => setSelected(e.target.value)}>
          <option value="">— wybierz scenariusz —</option>
          {scenarios.map((s) => (
            <option key={s.name} value={s.name}>
              {s.name}
            </option>
          ))}
        </select>
        <button type="button" onClick={onLoadClick} disabled={!selected}>
          Wczytaj
        </button>
        <button type="button" onClick={onDelete} disabled={!selected}>
          Usuń
        </button>
      </div>
      <div className="controls">
        <button type="button" onClick={onExport} disabled={scenarios.length === 0}>
          Eksportuj scenariusze
        </button>
        <button type="button" onClick={() => fileRef.current?.click()}>
          Importuj scenariusze
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="application/json,.json"
          className="sr-only"
          aria-label="Plik scenariuszy (JSON)"
          tabIndex={-1}
          onChange={(e) => {
            void onFile(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {info && !error && (
        <p role="status" className="note">
          {info}
        </p>
      )}
    </section>
  );
}
