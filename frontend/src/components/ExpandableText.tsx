export const SHORT_LIMIT = 160;

/** Początek tekstu do SHORT_LIMIT znaków: do końca pierwszego zdania, jeśli się mieści, inaczej twarde cięcie z „…”. */
function lead(text: string): string {
  const first = text.match(/^.*?[.!?](?=\s|$)/s)?.[0];
  if (first && first.length <= SHORT_LIMIT) return first;
  return `${text.slice(0, SHORT_LIMIT).trimEnd()}…`;
}

/** Długi opis w komórce tabeli: skrót widoczny od razu, całość pod natywnym <details> (klawiatura, bez stanu JS). */
export function ExpandableText({ text }: { text: string }) {
  const t = text.trim();
  if (t.length <= SHORT_LIMIT) return <p className="cell-text">{t}</p>;
  const head = lead(t);
  const rest = t.slice(head.endsWith("…") ? head.length - 1 : head.length).trimStart();
  return (
    <details className="expandable">
      <summary>
        <span className="expandable-lead">{head}</span> <span className="expandable-more">Pokaż więcej</span>
        <span className="expandable-less">Pokaż mniej</span>
      </summary>
      <p className="cell-text">{head.endsWith("…") ? `${head.slice(0, -1)}${rest}` : `${head} ${rest}`}</p>
    </details>
  );
}
