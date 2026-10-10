/**
 * Zapis scenariuszy (nazwany zestaw parametrów) w localStorage.
 * Moduł jest czysty i nigdy nie rzuca: gdy localStorage jest niedostępny
 * (tryb prywatny, limit, blokada) używana jest kopia w pamięci.
 * Schemat pliku/zapisu: {version: 1, scenarios: [{name, params, savedAt}]}.
 */
export const SCHEMA_VERSION = 1;
export const STORAGE_KEY = "symulator.scenarios.v1";
export const MAX_NAME_LENGTH = 60;
export const MAX_SCENARIOS = 50;
export const MAX_IMPORT_BYTES = 1024 * 1024;

export interface Scenario {
  name: string;
  params: Record<string, number>;
  savedAt: string;
}

export type StoreResult = { ok: true } | { ok: false; error: string };

let memory: Scenario[] = [];

/** Czyści kopię w pamięci (testy). */
export function resetScenarioStore(): void {
  memory = [];
}

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

function validName(name: unknown): string | null {
  if (typeof name !== "string") return "Nazwa scenariusza musi być tekstem.";
  const n = name.trim();
  if (!n) return "Nazwa scenariusza nie może być pusta.";
  if (n.length > MAX_NAME_LENGTH) return `Nazwa scenariusza jest za długa (maks. ${MAX_NAME_LENGTH} znaków).`;
  return null;
}

/** Wpis ze schematu albo null; `knownKeys` pominięte = bez kontroli kluczy. */
function parseEntry(raw: unknown, knownKeys?: ReadonlySet<string>): { entry?: Scenario; error?: string } {
  if (!isRecord(raw)) return { error: "Scenariusz ma nieprawidłowy format." };
  const nameError = validName(raw.name);
  if (nameError) return { error: nameError };
  const name = (raw.name as string).trim();
  if (!isRecord(raw.params)) return { error: `Scenariusz „${name}”: brak poprawnych parametrów.` };
  const params: Record<string, number> = {};
  for (const [k, v] of Object.entries(raw.params)) {
    if (k === "__proto__" || (knownKeys && !knownKeys.has(k))) return { error: `Scenariusz „${name}”: nieznany parametr „${k}”.` };
    if (typeof v !== "number" || !Number.isFinite(v)) return { error: `Scenariusz „${name}”: parametr „${k}” nie jest skończoną liczbą.` };
    params[k] = v;
  }
  const savedAt = typeof raw.savedAt === "string" && raw.savedAt.length <= 40 ? raw.savedAt : new Date().toISOString();
  return { entry: { name, params, savedAt } };
}

function readStored(): Scenario[] | null {
  let text: string | null;
  try {
    text = localStorage.getItem(STORAGE_KEY);
  } catch {
    return null; // niedostępny -> pamięć
  }
  if (text === null) return [];
  try {
    const doc: unknown = JSON.parse(text);
    if (!isRecord(doc) || doc.version !== SCHEMA_VERSION || !Array.isArray(doc.scenarios)) return [];
    const out: Scenario[] = [];
    for (const raw of doc.scenarios) {
      const { entry } = parseEntry(raw);
      if (entry && !out.some((s) => s.name === entry.name)) out.push(entry);
    }
    return out.slice(0, MAX_SCENARIOS);
  } catch {
    return [];
  }
}

export function listScenarios(): Scenario[] {
  return (readStored() ?? memory).map((s) => ({ ...s, params: { ...s.params } }));
}

function persist(list: Scenario[]): void {
  memory = list;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: SCHEMA_VERSION, scenarios: list }));
  } catch {
    /* tylko pamięć */
  }
}

export function saveScenario(name: string, params: Record<string, number>): StoreResult {
  const nameError = validName(name);
  if (nameError) return { ok: false, error: nameError };
  const parsed = parseEntry({ name, params });
  if (!parsed.entry) return { ok: false, error: parsed.error ?? "Nieprawidłowy scenariusz." };
  const entry = parsed.entry;
  const list = listScenarios();
  const i = list.findIndex((s) => s.name === entry.name);
  if (i >= 0) list[i] = entry;
  else if (list.length >= MAX_SCENARIOS) return { ok: false, error: `Osiągnięto limit ${MAX_SCENARIOS} scenariuszy – usuń któryś.` };
  else list.push(entry);
  persist(list);
  return { ok: true };
}

export function deleteScenario(name: string): void {
  persist(listScenarios().filter((s) => s.name !== name));
}

export function exportScenarios(): string {
  return JSON.stringify({ version: SCHEMA_VERSION, scenarios: listScenarios() }, null, 2);
}

/**
 * Wczytuje scenariusze z JSON-a (scalając je z istniejącymi; ta sama nazwa = nadpisanie).
 * Wszystko albo nic: przy pierwszym błędzie nic nie jest zapisywane.
 */
export function importScenarios(json: string, knownKeys?: ReadonlySet<string>): StoreResult {
  try {
    if (typeof json !== "string") return { ok: false, error: "Nieprawidłowy plik scenariuszy." };
    if (new TextEncoder().encode(json).length > MAX_IMPORT_BYTES) return { ok: false, error: "Plik jest za duży (maks. 1 MB)." };
    let doc: unknown;
    try {
      doc = JSON.parse(json);
    } catch {
      return { ok: false, error: "Plik nie jest poprawnym JSON-em." };
    }
    if (!isRecord(doc)) return { ok: false, error: "Nieprawidłowy format pliku scenariuszy." };
    if (doc.version !== SCHEMA_VERSION) {
      return { ok: false, error: `Nieobsługiwana wersja pliku (${String(doc.version ?? "brak")}); oczekiwana wersja ${SCHEMA_VERSION}.` };
    }
    if (!Array.isArray(doc.scenarios)) return { ok: false, error: "Pole „scenarios” musi być listą." };
    if (doc.scenarios.length > MAX_SCENARIOS) return { ok: false, error: `Za dużo scenariuszy (maks. ${MAX_SCENARIOS}).` };
    const incoming: Scenario[] = [];
    const seen = new Set<string>();
    for (const raw of doc.scenarios) {
      const { entry, error } = parseEntry(raw, knownKeys);
      if (!entry) return { ok: false, error: error ?? "Nieprawidłowy scenariusz." };
      if (seen.has(entry.name)) return { ok: false, error: `Powtórzona nazwa scenariusza „${entry.name}”.` };
      seen.add(entry.name);
      incoming.push(entry);
    }
    const merged = listScenarios().filter((s) => !seen.has(s.name)).concat(incoming);
    if (merged.length > MAX_SCENARIOS) return { ok: false, error: `Po imporcie przekroczono limit ${MAX_SCENARIOS} scenariuszy.` };
    persist(merged);
    return { ok: true };
  } catch {
    return { ok: false, error: "Nie udało się wczytać scenariuszy." };
  }
}
