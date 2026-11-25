import type { Method } from "./types";

export const METHOD_LABEL: Record<Method, string> = {
  ROSTRO: "Rostro",
  HUELLA: "Huella",
  "HUELLA+ROSTRO": "Huella + rostro",
  "CODIGO+ROSTRO": "Código + rostro",
  MANUAL: "Manual",
};

export const LIVENESS_LABEL: Record<string, string> = {
  SUPERADA: "Superada",
  DESACTIVADA: "Desactivada",
  NO_APLICA: "No aplica",
};

export function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return isoDate(d);
}

export function longDate(d: Date = new Date()): string {
  const text = new Intl.DateTimeFormat("es", { weekday: "long", day: "numeric", month: "long" }).format(d);
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function prettyDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat("es", { weekday: "short", day: "numeric", month: "short" }).format(new Date(y, m - 1, d));
}

export function score(v: number | null | undefined, digits = 3): string {
  return v === null || v === undefined ? "—" : v.toFixed(digits);
}

export function hours(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : v.toFixed(2);
}

export function pct(v: number): string {
  return `${(v * 100).toFixed(v > 0 && v < 0.01 ? 2 : 1)} %`;
}

export function localDateTimeInput(d: Date = new Date()): string {
  return `${isoDate(d)}T${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}
