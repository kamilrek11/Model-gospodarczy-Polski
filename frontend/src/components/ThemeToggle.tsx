import { useEffect, useState } from "react";
import { applyTheme, getStoredTheme, storeTheme, THEMES, type Theme } from "../theme";

const LABEL: Record<Theme, string> = { light: "Jasny", dark: "Ciemny", system: "Systemowy" };

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(getStoredTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const choose = (t: Theme) => {
    storeTheme(t);
    setTheme(t);
  };

  return (
    <div className="seg theme-toggle" role="group" aria-label="Motyw">
      {THEMES.map((t) => (
        <button key={t} type="button" aria-pressed={theme === t} onClick={() => choose(t)}>
          {LABEL[t]}
        </button>
      ))}
    </div>
  );
}
