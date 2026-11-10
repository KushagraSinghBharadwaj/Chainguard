import { useCallback, useEffect, useRef, useState } from "react";
import type { Report } from "../types/report";
import { analyzeAddress } from "../services/analyze";
import { ApiError } from "../services/http";
import { saveReport } from "../services/reportCache";
import { streamTransaction } from "../services/txStream";

export interface Step { id: string; label: string; status: string; ms?: number | null; note?: string }
export interface ScanState {
  phase: "idle" | "running" | "done" | "error";
  live: boolean; steps: Step[]; log: string[]; report: Report | null; error: string; elapsed: number;
}
const INIT: ScanState = { phase: "idle", live: false, steps: [], log: [], report: null, error: "", elapsed: 0 };

export function useScan() {
  const [state, setState] = useState<ScanState>(INIT);
  const ctl = useRef<AbortController | null>(null);
  const timer = useRef<number | undefined>(undefined);

  const stop = () => window.clearInterval(timer.current);
  const begin = () => {
    ctl.current?.abort();
    ctl.current = new AbortController();
    const t0 = performance.now();
    stop();
    timer.current = window.setInterval(() => setState((s) => ({ ...s, elapsed: Math.round(performance.now() - t0) })), 100);
    return ctl.current.signal;
  };
  const fail = (e: unknown) => {
    if (e instanceof DOMException && e.name === "AbortError") return;
    const msg = e instanceof ApiError ? e.message + (e.requestId ? " (ref " + e.requestId + ")" : "")
      : e instanceof Error && e.message ? e.message : "The backend is not reachable.";
    setState((s) => ({ ...s, phase: "error", error: msg }));
  };

  const reset = useCallback(() => { ctl.current?.abort(); window.clearInterval(timer.current); setState(INIT); }, []);
  useEffect(() => () => { ctl.current?.abort(); window.clearInterval(timer.current); }, []);

  const runAddress = useCallback(async (address: string) => {
    const signal = begin();
    setState({ ...INIT, phase: "running", steps: [{ id: "server", label: "Running every check on the server", status: "running" }], log: ["POST /v1/analyze  chain_id=1"] });
    try {
      const rep = await analyzeAddress(address, signal);
      const steps = (rep.coverage ?? []).map((c) => ({ id: c.check, label: c.check + " via " + (c.source ?? "n/a"), status: c.status, note: c.detail ?? undefined }));
      setState((s) => ({ ...s, phase: "done", steps, report: rep, log: [...s.log, "report received"] }));
    } catch (e) { fail(e); } finally { stop(); }
  }, []);

  const runTx = useCallback(async (to: string, data: string) => {
    const signal = begin();
    setState({ ...INIT, phase: "running", live: true, log: ["POST /v1/transactions/analyze/stream  chain_id=1"] });
    try {
      await streamTransaction(to, data, signal, (ev) => {
        if (ev.event === "start") setState((s) => ({ ...s, steps: ev.steps.map((x) => ({ id: x.id, label: x.label ?? x.id, status: "pending" })) }));
        else if (ev.event === "step") setState((s) => ({
          ...s,
          steps: s.steps.map((x) => (x.id === ev.id ? { ...x, status: ev.status, ms: ev.ms } : x)),
          log: [...s.log, "[" + ev.id + "] " + ev.status + (ev.ms != null ? " " + ev.ms + "ms" : "")],
        }));
        else if (ev.event === "report") { saveReport(ev.report); setState((s) => ({ ...s, phase: "done", report: ev.report, log: [...s.log, "report received"] })); }
        else if (ev.event === "error") throw new Error(ev.message);
      });
    } catch (e) { fail(e); } finally { stop(); }
  }, []);

  return { ...state, runAddress, runTx, reset };
}