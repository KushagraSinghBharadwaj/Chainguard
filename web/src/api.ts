const KEY = "cg_token";

async function register(): Promise<string> {
  const r = await fetch("/v1/clients/register", { method: "POST" });
  if (!r.ok) throw new Error("Could not create a client token (HTTP " + r.status + ").");
  const j = await r.json();
  localStorage.setItem(KEY, j.token);
  return j.token as string;
}

export async function post(path: string, body: unknown, signal?: AbortSignal, retry = true): Promise<Response> {
  const token = localStorage.getItem(KEY) ?? (await register());
  const r = await fetch("/v1" + path, {
    method: "POST",
    headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (r.status === 401 && retry) {
    localStorage.removeItem(KEY);
    return post(path, body, signal, false);
  }
  return r;
}

export async function errorText(r: Response): Promise<string> {
  try {
    const j = await r.json();
    return "HTTP " + r.status + ": " + (j.message ?? j.detail?.message ?? JSON.stringify(j.detail ?? j));
  } catch {
    return "HTTP " + r.status;
  }
}

export async function readLines(r: Response, onObj: (o: any) => void): Promise<void> {
  const reader = r.body!.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (value) buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (line) {
        try { onObj(JSON.parse(line)); } catch { /* skip malformed line */ }
      }
    }
    if (done) break;
  }
}
