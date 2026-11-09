import { useRef, useState } from "react";
import { errorText, post, readLines } from "./api";

type Mode = "wallet" | "token" | "tx";
type Step = { id: string; label: string; status: string; ms?: number; note?: string };

const ADDR = /^0x[0-9a-fA-F]{40}$/;
const DATA = /^0x([0-9a-fA-F]{2})*$/;
const FILE: Record<Mode, string> = { wallet: "wallet.check", token: "token.check", tx: "transaction.check" };
const PATH: Record<Mode, string> = { wallet: "/wallets/analyze", token: "/tokens/analyze", tx: "/transactions/analyze/stream" };
const MARK: Record<string, string> = { done: "✓", completed: "✓", running: "…", pending: "○", partial: "~", unavailable: "✗", skipped: "-" };
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export default function App() {
  const [mode, setMode] = useState<Mode>("wallet");
  const [addr, setAddr] = useState("");
  const [data, setData] = useState("0x");
  const [busy, setBusy] = useState(false);
  const [steps, setSteps] = useState<Step[]>([]);
  const [log, setLog] = useState<string[]>([]);
  const [report, setReport] = useState<any>(null);
  const [err, setErr] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const ctrl = useRef<AbortController | null>(null);

  const say = (l: string) => setLog((p) => [...p, l]);
  const patch = (id: string, p: Partial<Step>) => setSteps((s) => s.map((x) => (x.id === id ? { ...x, ...p } : x)));

  async function run() {
    setErr(""); setReport(null); setSteps([]); setLog([]);
    if (!ADDR.test(addr)) return setErr("Enter a 42-character address that starts with 0x.");
    if (mode === "tx" && !DATA.test(data)) return setErr("Calldata must be hex that starts with 0x.");
    ctrl.current = new AbortController();
    setBusy(true);
    const t0 = performance.now();
    const timer = setInterval(() => setElapsed(Math.round(performance.now() - t0)), 100);
    const body = mode === "wallet" || mode === "token" ? { chain_id: 1, address: addr } : { chain_id: 1, to: addr, data };
    say(`$ POST /v1${PATH[mode]}  chain_id=1`);
    try {
      const res = await post(PATH[mode], body, ctrl.current.signal);
      if (!res.ok) throw new Error(await errorText(res));
      if (mode === "tx") {
        await readLines(res, (o) => {
          if (o.event === "start") setSteps(o.steps.map((s: any) => ({ ...s, status: "pending" })));
          else if (o.event === "step") { patch(o.id, { status: o.status, ms: o.ms }); say(`[${o.id}] ${o.status}${o.ms != null ? " " + o.ms + "ms" : ""}`); }
          else if (o.event === "report") { setReport(o.report); say("report received"); }
          else if (o.event === "error") throw new Error(o.message);
        });
      } else {
        say("server is running every check. This endpoint returns one result at the end.");
        setSteps([{ id: "server", label: "run all checks on the server", status: "running" }]);
        const rep = await res.json();
        say(`report received after ${Math.round(performance.now() - t0)}ms. Listing each check:`);
        setSteps([]);
        for (const c of rep.coverage) {
          setSteps((p) => [...p, { id: c.check, label: `${c.check} via ${c.source ?? "n/a"}`, status: c.status, note: c.detail ?? undefined }]);
          say(`[${c.check}] ${c.status}${c.detail ? " (" + c.detail + ")" : ""}`);
          await sleep(110);
        }
        setReport(rep);
      }
    } catch (e: any) {
      if (e.name !== "AbortError") setErr(e.message || "The backend is not reachable on port 8000.");
    } finally {
      clearInterval(timer); setBusy(false);
    }
  }

  return (
    <div className="app">
      <header className="top">
        <span className="brand">chainguard<i>.sh</i></span>
        <span className="muted">read-only · Ethereum mainnet · never signs, never holds funds</span>
      </header>

      <section className="hero">
        <p className="c">// screening that shows its work</p>
        <h1><span className="k">const</span> verdict <span className="o">=</span> <span className="f">await</span> chainguard.<span className="f">check</span>(<span className="s">address</span>);</h1>
        <p className="lead">Paste a wallet, token or transaction. Watch every real check run against live sources, then read the evidence behind the risk level. Nothing here is typed in by hand.</p>
      </section>

      <main className="win">
        <div className="tabs">
          {(Object.keys(FILE) as Mode[]).map((m) => (
            <button key={m} className={"tab" + (m === mode ? " on" : "")} onClick={() => !busy && setMode(m)}>{FILE[m]}</button>
          ))}
        </div>
        <div className="ed">
          <label className="row"><span className="ln">1</span><span className="k">address</span><span className="o">=</span>
            <input value={addr} onChange={(e) => setAddr(e.target.value.trim())} placeholder="0x…" spellCheck={false} />
          </label>
          {mode === "tx" && (
            <label className="row"><span className="ln">2</span><span className="k">calldata</span><span className="o">=</span>
              <input value={data} onChange={(e) => setData(e.target.value.trim())} spellCheck={false} />
            </label>
          )}
          <div className="row act">
            <button className="run" disabled={busy} onClick={run}>{busy ? `running ${elapsed}ms` : "run check"}</button>
            {busy && <button className="ghost" onClick={() => ctrl.current?.abort()}>stop</button>}
          </div>
          {err && <p className="err">error: {err}</p>}
        </div>

        {(steps.length > 0 || log.length > 0) && (
          <div className="term">
            <div className="pane">TERMINAL</div>
            <ul className="steps">
              {steps.map((s) => (
                <li key={s.id} className={"st " + s.status}>
                  <b>{MARK[s.status] ?? "?"}</b> {s.label}
                  <span className="muted"> {s.status}{s.ms != null ? ` ${s.ms}ms` : ""}{s.note ? ` (${s.note})` : ""}</span>
                </li>
              ))}
            </ul>
            <pre className="log">{log.join("\n")}</pre>
          </div>
        )}

        {report && <Report r={report} />}
      </main>

      <footer className="status">
        <span>{report ? `${report.engine_version}` : "ready"}</span>
        <span>{report ? new Date(report.generated_at).toLocaleString() : "screening result, not a guarantee of safety"}</span>
      </footer>
    </div>
  );
}

function Report({ r }: { r: any }) {
  const m = r.model ?? {};
  return (
    <div className="rep">
      <div className="pane">PROBLEMS</div>
      <div className={"lvl " + r.risk_level}>{r.risk_level.replace("_", " ")}</div>
      <p className="sum">{r.summary}</p>

      <h3>evidence ({r.evidence.length})</h3>
      {r.evidence.length === 0 && <p className="muted">No findings in the checks that completed.</p>}
      {r.evidence.map((e: any) => (
        <details key={e.id} className={"ev " + e.severity}>
          <summary>
            <span className="sev">{e.severity}</span> {e.claim}
            <span className="muted"> · {e.source?.name}{e.verified ? " · verified" : ""} · confidence {Math.round(e.confidence * 100)}%</span>
          </summary>
          <pre>{JSON.stringify({ id: e.id, kind: e.kind, fetched_at: e.source?.fetched_at, data: e.data }, null, 2)}</pre>
        </details>
      ))}

      <h3>coverage</h3>
      <ul className="plain">
        {r.coverage.map((c: any) => (
          <li key={c.check} className={"st " + c.status}><b>{MARK[c.status]}</b> {c.check} <span className="muted">{c.source ?? ""} {c.status}{c.detail ? ` (${c.detail})` : ""}</span></li>
        ))}
      </ul>

      <h3>model</h3>
      <p className="muted">status: {m.status}{m.version ? ` · ${m.version}` : ""}{m.status !== "available" ? " · no score is shown" : ""}</p>
      {m.status === "available" && <pre>{JSON.stringify(m, null, 2)}</pre>}

      {r.consequences?.length > 0 && (<><h3>what it could mean</h3><ul className="plain">{r.consequences.map((c: string) => <li key={c}>{c}</li>)}</ul></>)}
      <h3>limitations</h3>
      <ul className="plain">{r.limitations.map((l: string) => <li key={l} className="muted">{l}</li>)}</ul>
      <h3>sources</h3>
      <ul className="plain">{r.data_sources.map((s: any) => <li key={s.name} className="muted">{s.name} · {s.fetched_at ?? "time unknown"}</li>)}</ul>
    </div>
  );
}
