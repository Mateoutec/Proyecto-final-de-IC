export class ApiError extends Error {
  status: number;
  code?: string;
  data: Record<string, unknown> | null;

  constructor(message: string, status: number, code?: string, data: Record<string, unknown> | null = null) {
    super(message);
    this.status = status;
    this.code = code;
    this.data = data;
  }
}

type Options = Omit<RequestInit, "body"> & { json?: unknown; body?: BodyInit | null };

let onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const headers = new Headers(opts.headers);
  let body = opts.body;
  if (opts.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(opts.json);
  }
  let res: Response;
  try {
    res = await fetch(path, { ...opts, headers, body, credentials: "same-origin" });
  } catch {
    throw new ApiError("Sin conexión con el servidor local. Revisa que scripts/start.sh siga corriendo.", 0, "offline");
  }
  const isJson = (res.headers.get("content-type") || "").includes("application/json");
  const data = isJson ? await res.json().catch(() => null) : null;
  if (!res.ok) {
    if (res.status === 401 && path.startsWith("/api/admin") && !path.endsWith("/login")) onUnauthorized?.();
    const detail = (data && typeof data.detail === "string" && data.detail) || `Error ${res.status} del servidor`;
    throw new ApiError(detail, res.status, data?.code, data);
  }
  return data as T;
}

export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export async function downloadFile(url: string): Promise<{ filename: string; rows: number | null }> {
  let res: Response;
  try {
    res = await fetch(url, { credentials: "same-origin" });
  } catch {
    throw new ApiError("Sin conexión con el servidor local", 0, "offline");
  }
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    if (res.status === 401) onUnauthorized?.();
    throw new ApiError(data?.detail || `Error ${res.status}`, res.status, data?.code, data);
  }
  const disposition = res.headers.get("content-disposition") || "";
  const match = /filename="?([^"]+)"?/.exec(disposition);
  const filename = match?.[1] || "exportacion";
  const blob = await res.blob();
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 2000);
  const rows = res.headers.get("x-rows");
  return { filename, rows: rows ? Number(rows) : null };
}
