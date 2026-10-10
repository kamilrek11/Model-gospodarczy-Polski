import type { TaxKey } from "../api/types";

/**
 * Paleta kategorialna odporna na daltonizm (sloty 1-3 palety referencyjnej dataviz:
 * niebieski, pomarańczowy, morski). Zweryfikowana validate_palette.js w trybie jasnym
 * i ciemnym (CVD ΔE >= 9,2; normalny wzrok ΔE >= 26). Wartości jasne/ciemne są
 * zdefiniowane jako zmienne CSS w styles.css (:root, @media dark, [data-theme="dark"]),
 * dzięki czemu przełącznik motywu (Task 10) nie wymaga zmian w kodzie wykresów.
 *
 * Jasny slot 3 ma kontrast < 3:1 na jasnym tle, więc tożsamość serii nigdy nie
 * opiera się wyłącznie na kolorze: legenda z etykietami + tabela danych.
 */
export const TAX_COLOR: Record<TaxKey, string> = {
  pit: "var(--series-1)",
  cit: "var(--series-2)",
  vat: "var(--series-3)",
};

export const TAX_LABEL: Record<TaxKey, string> = { pit: "PIT", cit: "CIT", vat: "VAT" };
export const TAX_ORDER: TaxKey[] = ["pit", "cit", "vat"];

export const INK = {
  primary: "var(--text-primary)",
  secondary: "var(--text-secondary)",
  grid: "var(--grid)",
  surface: "var(--surface-1)",
} as const;
