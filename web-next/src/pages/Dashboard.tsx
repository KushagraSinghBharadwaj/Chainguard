import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { listHistory } from "../services/history";
import { allReports } from "../services/reportCache";
import { ApiError } from "../services/http";
import { useHealth } from "../hooks/useHealth";
import RiskBadge from "../components/report/RiskBadge";
import type { HistoryItem, RiskLevel } from "../types/report";
import "./dashboard.css";

const LEVELS: RiskLevel[] = ["LOW", "MODERATE", "HIGH", "CRITICAL", "INSUFFICIENT_DATA"];
const VAR: Record<RiskLevel, string> = { LOW: "--lvl-low", MODERATE: "--lvl-moderate", HIGH: "--lvl-high", CRITICAL: "--lvl-critical", INSUFFICIENT_DATA: "--lvl-insufficient" };
const NAME: Record<RiskLevel, string> = { LOW: "Low", MODERATE: "Moderate", HIGH: "High", CRITICAL: "Critical", INSUFFICIENT_DATA: "Insufficient data" };
const short = (k: string) => (k.length > 18 ? k.slice(0, 10) + "…" + k.slice(-6) : k);

export default function Dashboard() {
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  const [err, setErr] = useState("");
  const { state, data } = useHealth();
  const cached = useMemo(() => allReports(), []);

  useEffect(() => {
    listHistory(100).then(setItems).catch((e) => setErr(e instanceof ApiError ? e.message : "The backend is not reachable."));
  }, []);

  const total = items?.length ?? 0;
  const count = (f: (i: HistoryItem) => boolean) => (items ?? []).filter(f).length;
  const prov = useMemo(() => {
    const m: Record<string, { c: number; p: number; o: number }> = {};
    cached.forEach((r) => (r.coverage ?? []).forEach((c) => (c.source ?? "n/a").split(",").forEach((s) => {
      const e = (m[s.trim()] ??= { c: 0, p: 0, o: 0 });
      if (c.status === "completed") e.c++; else if (c.status === "partial") e.p++; else e.o++;
    })));
    return Object.entries(m);
  }, [cached]);
  const model = cached.find((r) => r.model)?.model;

  return (
    <section className="wrap dash">
      <h1>Dashboard</h1>
      <p className="muted">Built from your own checks in this browser's client. These are not platform-wide totals.</p>
      {err && <p className="err box" role="alert">{err}</p>}

      <div className="tiles">
        {([["Total checks", total], ["Wallet analyses", count((i) => i.subject_type === "wallet")], ["Token analyses", count((i) => i.subject_type === "token")], ["Transaction analyses", count((i) => i.subject_type === "transaction")]] as const).map(([l, n], i) => (
          <div key={l} className="glass tile" style={{ ["--i" as string]: i }}><span className="muted">{l}</span><b>{items ? n : "–"}</b></div>
        ))}
      </div>
      {total >= 100 && <p className="muted small">Counts cover your most recent 100 checks.</p>}

      <div className="dgrid">
        <section className="glass pad">
          <h3>Risk distribution</h3>
          {!items ? <p className="muted">Loading…</p> : total === 0 ? <p className="muted">No checks yet. <Link to="/scan">Run a scan</Link> to see results here.</p> : (
            <ul className="bars">{LEVELS.map((l) => {
              const n = count((i) => i.risk_level === l);
              return (
                <li key={l}><span>{NAME[l]}</span>
                  <div className="track"><div className="fill" style={{ width: (n / total) * 100 + "%", background: "var(" + VAR[l] + ")" }} /></div>
                  <b>{n}</b></li>
              );
            })}</ul>
          )}
          <p className="muted small">Low means no findings in completed checks. It is not a safety guarantee.</p>
        </section>

        <section className="glass pad">
          <h3>System status</h3>
          <ul className="plain">
            <li><b>API:</b> {state}{data ? " · v" + data.version : ""}</li>
            <li><b>Database:</b> {data?.database ?? "unknown"}</li>
            <li><b>Model:</b> {model ? model.status + (model.reason ? " · " + model.reason : "") : "no cached report yet"}</li>
          </ul>
          <p className="muted small">Machine-learning output is experimental and is shown only when the backend provides a valid score.</p>
        </section>

        <section className="glass pad">
          <h3>Provider activity</h3>
          {prov.length === 0 ? <p className="muted">Appears after you run a scan. Shows what completed or was partial in your cached reports.</p> : (
            <ul className="plain">{prov.map(([k, v]) => <li key={k}><b>{k}</b> <span className="muted">· {v.c} completed · {v.p} partial · {v.o} other (across {cached.length} cached reports)</span></li>)}</ul>
          )}
        </section>

        <section className="glass pad">
          <h3>Recent activity</h3>
          {!items ? <p className="muted">Loading…</p> : items.length === 0 ? <p className="muted">Nothing yet.</p> : (
            <ul className="recent">{items.slice(0, 6).map((i) => (
              <li key={i.report_id}><RiskBadge level={i.risk_level} /><span className="mono">{short(i.subject_key)}</span><span className="muted">{i.subject_type} · {new Date(i.created_at).toLocaleString()}</span></li>
            ))}</ul>
          )}
          <Link className="btn ghost sm" to="/history">Open history</Link>
        </section>
      </div>
    </section>
  );
}