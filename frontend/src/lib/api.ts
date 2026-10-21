/** Typed fetch client. Session is a secure httpOnly cookie — no tokens in storage. */

export class ApiError extends Error {
  status: number;
  code: string;
  details?: unknown;
  requestId?: string;
  constructor(status: number, code: string, message: string, details?: unknown, requestId?: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

type Opts = { method?: string; body?: unknown; idempotencyKey?: string; raw?: boolean };

export async function api<T = unknown>(path: string, opts: Opts = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.idempotencyKey) headers["Idempotency-Key"] = opts.idempotencyKey;

  const res = await fetch(`/api${path.startsWith("/") ? path : `/${path}`}`, {
    method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"),
    credentials: "include",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });

  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = undefined;
  try { data = text ? JSON.parse(text) : undefined; } catch { data = text; }

  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string; details?: unknown; request_id?: string } })?.error;
    throw new ApiError(res.status, err?.code ?? "HTTP_ERROR", err?.message ?? res.statusText, err?.details, err?.request_id);
  }
  return data as T;
}

export async function apiUpload<T = unknown>(path: string, file: File, field = "file"): Promise<T> {
  const form = new FormData();
  form.append(field, file);
  const res = await fetch(`/api${path}`, { method: "POST", credentials: "include", body: form });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = data?.error;
    throw new ApiError(res.status, err?.code ?? "HTTP_ERROR", err?.message ?? res.statusText, err?.details);
  }
  return data as T;
}

export const get = <T,>(p: string) => api<T>(p);
export const post = <T,>(p: string, body?: unknown, idem?: string) =>
  api<T>(p, { method: "POST", body, idempotencyKey: idem });
export const put = <T,>(p: string, body?: unknown) => api<T>(p, { method: "PUT", body });
export const patch = <T,>(p: string, body?: unknown) => api<T>(p, { method: "PATCH", body });
export const del = (p: string) => api(p, { method: "DELETE" });

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}
