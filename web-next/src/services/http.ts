const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";
const KEY = "cgx_client";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public requestId?: string) { super(message); }
}
interface Stored { token: string; expires_at: string }

const load = (): Stored | null => { try { const v = localStorage.getItem(KEY); return v ? JSON.parse(v) : null; } catch { return null; } };
const save = (s: Stored) => { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { /* storage unavailable */ } };

export async function toError(r: Response): Promise<ApiError> {
  let code = "http_" + r.status, msg = "Request failed (HTTP " + r.status + ").", rid: string | undefined;
  try {
    const j = await r.json(); const e = j.error ?? j.detail;
    if (e && typeof e === "object") { code = e.code ?? code; msg = e.message ?? msg; rid = e.request_id; }
  } catch { /* non-JSON body */ }
  if (r.status === 429) msg = "Too many requests. Wait a moment and try again.";
  return new ApiError(r.status, code, msg, rid);
}

let pending: Promise<string> | null = null;
function obtain(old?: string): Promise<string> {
  if (pending) return pending;
  pending = (async () => {
    try {
      if (old) {
        const r = await fetch(BASE + "/v1/clients/token/refresh", { method: "POST", headers: { Authorization: "Bearer " + old } });
        if (r.ok) { const j = await r.json(); save({ token: j.token, expires_at: j.expires_at }); return j.token as string; }
      }
      const r = await fetch(BASE + "/v1/clients/register", { method: "POST" });
      if (!r.ok) throw await toError(r);
      const j = await r.json(); save({ token: j.token, expires_at: j.expires_at });
      return j.token as string;
    } finally { pending = null; }
  })();
  return pending;
}

export async function authFetch(path: string, init: RequestInit = {}, retry = true): Promise<Response> {
  const token = load()?.token ?? (await obtain());
  const r = await fetch(BASE + path, { ...init, headers: { ...(init.headers as Record<string, string>), Authorization: "Bearer " + token } });
  if (r.status === 401 && retry) { await obtain(token); return authFetch(path, init, false); }
  return r;
}
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await authFetch(path, init);
  if (!r.ok) throw await toError(r);
  return r.json() as Promise<T>;
}
export const postJson = <T,>(path: string, body: unknown, signal?: AbortSignal) =>
  api<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
export const apiBase = BASE;