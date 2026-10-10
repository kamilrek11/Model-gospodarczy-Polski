export type Theme = "light" | "dark" | "system";
export const THEME_KEY = "symulator.theme";
export const THEMES: Theme[] = ["light", "dark", "system"];

export function getStoredTheme(): Theme {
  try {
    const v = localStorage.getItem(THEME_KEY);
    if (v === "light" || v === "dark") return v;
  } catch {
    /* localStorage zablokowany */
  }
  return "system";
}

export function storeTheme(theme: Theme): void {
  try {
    if (theme === "system") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* bez trwałości */
  }
}

/** light/dark ustawiają data-theme na <html>; system je usuwa (decyduje prefers-color-scheme). */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}
