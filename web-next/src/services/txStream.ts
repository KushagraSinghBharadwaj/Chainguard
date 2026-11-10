import type { Report } from "../types/report";
import { authFetch, toError } from "./http";

export type TxEvent =
  | { event: "start"; steps: { id: string; label?: string }[] }
  | { event: "step"; id: string; status: string; ms?: number | null }
  | { event: "report"; report: Report }
  | { event: "error"; message: string };

export async function streamTransaction(to: string, data: string, signal: AbortSignal, onEvent: (e: TxEvent) => void): Promise<void> {
  const res = await authFetch("/v1/transactions/analyze/stream", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chain_id: 1, to, data }), signal,
  });
  if (!res.ok) throw await toError(res);
  if (!res.body) throw new Error("The server sent no stream.");
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (line) onEvent(JSON.parse(line) as TxEvent);
    }
  }
  const tail = buf.trim();
  if (tail) onEvent(JSON.parse(tail) as TxEvent);
}