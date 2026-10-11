import { useEffect, useId, useRef, useState } from "react";
import type { ParamSpec, TaxKey } from "../api/types";

export const TAX_TITLES: Record<TaxKey, string> = {
  pit: "PIT – podatek dochodowy od osób fizycznych",
  cit: "CIT – podatek dochodowy od osób prawnych",
  vat: "VAT – podatek od towarów i usług",
};
const TAX_ORDER: TaxKey[] = ["pit", "cit", "vat"];

const isFraction = (s: ParamSpec) => s.unit === "ułamek";
const round = (x: number) => Math.round(x * 1e6) / 1e6;
const toDisplay = (s: ParamSpec, v: number) => (isFraction(s) ? round(v * 100) : v);
const fromDisplay = (s: ParamSpec, v: number) => (isFraction(s) ? round(v / 100) : v);
const unitLabel = (s: ParamSpec) => (isFraction(s) ? "%" : s.unit);
const fmt = (s: ParamSpec, v: number) => `${toDisplay(s, v).toLocaleString("pl-PL")}${isFraction(s) ? "%" : ` ${s.unit}`}`;

interface Props {
  schema: ParamSpec[];
  values: Record<string, number>;
  onChange: (key: string, value: number) => void;
  onReset: () => void;
}

export function ParameterPanel({ schema, values, onChange, onReset }: Props) {
  const [resetKey, setResetKey] = useState(0);
  return (
    <div className="parameter-panel">
      <button
        type="button"
        className="reset-all"
        onClick={() => {
          setResetKey((k) => k + 1);
          onReset();
        }}
      >
        Przywróć wszystko
      </button>
      {TAX_ORDER.map((tax) => {
        const specs = schema.filter((s) => s.tax === tax);
        if (specs.length === 0) return null;
        return <TaxSection key={tax} tax={tax} specs={specs} values={values} onChange={onChange} resetKey={resetKey} />;
      })}
    </div>
  );
}

function TaxSection({
  tax,
  specs,
  values,
  onChange,
  resetKey,
}: { tax: TaxKey; specs: ParamSpec[]; resetKey: number } & Pick<Props, "values" | "onChange">) {
  const headingId = useId();
  return (
    <details open role="group" aria-labelledby={headingId} className="tax-section">
      <summary id={headingId}>{TAX_TITLES[tax]}</summary>
      {specs.map((s) => (
        <ParamRow key={s.key} spec={s} value={values[s.key] ?? s.default} onChange={onChange} resetKey={resetKey} />
      ))}
    </details>
  );
}

function ParamRow({
  spec,
  value,
  onChange,
  resetKey,
}: {
  spec: ParamSpec;
  value: number;
  onChange: Props["onChange"];
  resetKey: number;
}) {
  const id = useId();
  const descId = `${id}-desc`;
  const errId = `${id}-err`;
  const [text, setText] = useState(String(toDisplay(spec, value)));
  const [error, setError] = useState<string | null>(null);
  const dMin = toDisplay(spec, spec.min);
  const dMax = toDisplay(spec, spec.max);
  const dStep = isFraction(spec) ? round(spec.step * 100) : spec.step;
  const deviates = value !== spec.default;

  // Synchronizacja pola po zewnętrznej zmianie wartości (np. przywrócenie), bez psucia pisania.
  useEffect(() => {
    setText((t) => (fromDisplay(spec, Number(t)) === value ? t : String(toDisplay(spec, value))));
    setError(null);
  }, [value, spec]);

  // "Przywróć wszystko": wyczyść lokalny tekst i błąd także gdy wartość się nie zmienia.
  const lastReset = useRef(resetKey);
  useEffect(() => {
    if (lastReset.current === resetKey) return;
    lastReset.current = resetKey;
    setText(String(toDisplay(spec, spec.default)));
    setError(null);
  }, [resetKey, spec]);

  function handleText(raw: string) {
    setText(raw);
    const n = Number(raw.replace(",", "."));
    if (raw.trim() === "" || !Number.isFinite(n)) {
      setError("Podaj poprawną liczbę");
      return;
    }
    if (n < dMin || n > dMax) {
      setError(`Wartość poza zakresem (${dMin}–${dMax} ${unitLabel(spec)})`);
      return;
    }
    setError(null);
    onChange(spec.key, fromDisplay(spec, n));
  }

  function restore() {
    setError(null);
    setText(String(toDisplay(spec, spec.default)));
    onChange(spec.key, spec.default);
  }

  return (
    <div className={`param-row${deviates ? " deviates" : ""}`} title={spec.description}>
      <label htmlFor={id}>{spec.label}</label>
      {deviates && (
        <span data-testid={`deviation-${spec.key}`} className="deviation-marker" title="Wartość różni się od bazowej">
          ● zmieniono
        </span>
      )}
      <div className="controls">
        <input
          id={id}
          type="text"
          inputMode="decimal"
          value={text}
          onChange={(e) => handleText(e.target.value)}
          aria-invalid={error ? "true" : "false"}
          aria-describedby={`${descId}${error ? ` ${errId}` : ""}`}
        />
        <span className="unit">{unitLabel(spec)}</span>
        <input
          type="range"
          aria-label={`${spec.label} – suwak`}
          min={dMin}
          max={dMax}
          step={dStep}
          value={toDisplay(spec, value)}
          onChange={(e) => {
            const n = Number(e.target.value);
            setText(String(n));
            setError(null);
            onChange(spec.key, fromDisplay(spec, n));
          }}
        />
        <button type="button" onClick={restore} disabled={!deviates && error === null} aria-label={`Przywróć ${spec.label}`}>
          Przywróć
        </button>
      </div>
      {error && (
        <div id={errId} role="alert" className="error">
          {error}
        </div>
      )}
      <small id={descId}>
        {spec.description} · Baza: {fmt(spec, spec.default)}
      </small>
    </div>
  );
}
