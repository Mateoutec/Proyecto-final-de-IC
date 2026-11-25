export type ThemePref = "light" | "dark" | "system";

const KEY = "asistencia.theme";

function read(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch {
    /* almacenamiento bloqueado */
  }
  return "system";
}

function systemDark(): boolean {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

export function resolvedTheme(pref: ThemePref = read()): "light" | "dark" {
  return pref === "system" ? (systemDark() ? "dark" : "light") : pref;
}

function apply(pref: ThemePref) {
  document.documentElement.classList.toggle("dark", resolvedTheme(pref) === "dark");
}

export function initTheme() {
  apply(read());
  window.matchMedia?.("(prefers-color-scheme: dark)").addEventListener?.("change", () => apply(read()));
}

export function getThemePref(): ThemePref {
  return read();
}

export function setThemePref(pref: ThemePref) {
  try {
    localStorage.setItem(KEY, pref);
  } catch {
    /* almacenamiento bloqueado */
  }
  apply(pref);
}

export function toggleTheme(): "light" | "dark" {
  const next = resolvedTheme() === "dark" ? "light" : "dark";
  setThemePref(next);
  return next;
}

export function readPref(key: string, fallback: string): string {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

export function writePref(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* almacenamiento bloqueado */
  }
}
