import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { listHistory } from "../services/history";
import { getReport } from "../services/reportCache";
import { ApiError } from "../services/http";
import RiskBadge from "../components/report/RiskBadge";
import type { HistoryItem } from "../types/report";
import "./dashboard.css";

export default function History() {
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [level, setLevel] = useState("");
  const [type, setType] = useState("");

  useEffect(() => {
    listHistory(100).then(setItems).catch((e) => setErr(e instanceof ApiError ? e.message : "The backend is not reachable."));
  }, []);

  const shown = useMemo(() => {
    const s = q.trim().toLowerCase();
    return (items ?? []).filter((i) => (!level || i.risk_level === level) && (!type || i.subject_type === type) && (!s || i.subject_key.toLowerCase().includes(s) || i.summary.toLowerCase().includes(s)));
  }, [items, q, level, type]);

  return (
    <section className="wrap dash">
      <h1>History</h1>
      <p className="muted">Your checks from this browser's client, newest first (up to 100).</p>
      <div className="glass filters">
        <div className="field"><label htmlFor="q">Search address or summary</label><input id="q" value={q} onChange={(e) => setQ(e.target.value)} placeholder="0x…" /></div>
        <div className="field"><label htmlFor="lv">Risk level</label>
          <select id="lv" value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="">All</option>{["LOW", "MODERATE", "HIGH", "CRITICAL", "INSUFFICIENT_DATA"].map((l) => <option key={l} value={l}>{l}</option>)}
          </select></div>
        <div className="field"><label htmlFor="ty">Type</label>
          <select id="ty" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">All</option><option value="wallet">Wallet</option><option value="token">Token</option><option value="transaction">Transaction</option>
          </select></div>
      </div>

      {err && <p className="err box" role="alert">{err}</p>}
      {!items && !err && <p className="muted">Loading…</p>}
      {items && items.length === 0 && <p className="muted">No checks yet. <Link to="/scan">Run a scan</Link>.</p>}
      {items && items.length > 0 && shown.length === 0 && <p className="muted">No checks match these filters.</p>}

      <ol className="timeline">
        {shown.map((i) => {
          const cached = !!getReport(i.report_id);
          return (
            <li key={i.report_id} className="glass item">
              <div className="top"><RiskBadge level={i.risk_level} /><span className="muted">{i.subject_type} · {new Date(i.created_at).toLocaleString()}</span></div>
              <p className="mono key">{i.subject_key}</p>
              <p className="muted sm">{i.summary}</p>
              <div className="acts">
                {cached ? <Link className="btn ghost sm" to={"/report/" + i.report_id}>Open report</Link>
                  : i.subject_type !== "transaction" ? <Link className="btn ghost sm" to={"/scan/" + i.subject_type + "?address=" + i.subject_key}>Re-run (fills the form)</Link>
                  : <span className="muted sm">Calldata is not stored, so this check cannot be re-run.</span>}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}