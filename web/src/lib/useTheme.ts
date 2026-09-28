import { useEffect, useState } from "react";

type Theme = "light" | "dark";

function getInitialTheme(): Theme {
  try {
    const saved = localStorage.getItem("dblp-theme");
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    // localStorage unavailable (private mode, etc.) - fall through to system preference.
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** P8 (polish): dark mode toggle. Light/dark come free from the §9.1 CSS
 * tokens already defined under `[data-theme="dark"]` - this just flips the
 * attribute and remembers the choice per browser. */
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("dblp-theme", theme);
    } catch {
      // Best-effort only - a per-viewer convenience, not state anything depends on.
    }
  }, [theme]);

  return [theme, () => setTheme((t) => (t === "light" ? "dark" : "light"))];
}
