import type { ReactNode } from "react";

interface Props {
  caption: string;
  /** Nagłówek pierwszej kolumny (np. "Rok") + nagłówki pozostałych. */
  columns: string[];
  rows: ReactNode[][];
  summary?: string;
}

/** Tabela jako tekstowa alternatywa wykresu, zwinięta w <details>. */
export function DataTable({ caption, columns, rows, summary = "Pokaż dane w tabeli" }: Props) {
  return (
    <details className="data-details">
      <summary>{summary}</summary>
      <div className="table-scroll">
        <table className="data-table">
          <caption>{caption}</caption>
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c} scope="col">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {r.map((cell, j) =>
                  j === 0 ? (
                    <th key={j} scope="row">
                      {cell}
                    </th>
                  ) : (
                    <td key={j}>{cell}</td>
                  ),
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
