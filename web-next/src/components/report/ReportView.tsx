import type { Report, RiskLevel } from "../../types/report";
import RiskBadge, { LEVEL_NOTE } from "./RiskBadge";
import DownloadPdfButton from "./DownloadPdfButton";
import "./report.css";

export const fmt = (s: string) => { const d = new Date(s); return isNaN(+d) ? s : d.toLocaleString(); };

export default function ReportView({ r }: { r: Report }) {
  const level = (LEVEL_NOTE[r.risk_level] ? r.risk_level : "INSUFFICIENT_DATA") as RiskLevel;
  const evidence = r.evidence ?? [], coverage = r.coverage ?? [], limits = r.limitations ?? [], sources = r.data_sources ?? [];
  const scoreOk = typeof r.model?.score === "number" && r.model.status !== "not_reliable" && r.model.status !== "unavailable";
  return (
    <article className="rv">
      <header className={"rv-head glass lv-" + level.toLowerCase().replace("_", "-")}>
        <RiskBadge level={level} />
        <p className="sum">{r.summary}</p>
        <p className="note">{LEVEL_NOTE[level]}</p>
        <div className="dl-row"><DownloadPdfButton report={r} /></div>
        <dl className="meta">
          <div><dt>Subject</dt><dd className="mono">{r.subject?.key}</dd></div>
          <div><dt>Type</dt><dd>{r.detected_address_type ? r.subject?.type + " (" + r.detected_address_type + ")" : r.subject?.type}</dd></div>
          <div><dt>Generated</dt><dd>{fmt(r.generated_at)}</dd></div>
          <div><dt>Engine</dt><dd className="mono">{r.engine_version}</dd></div>
        </dl>
      </header>

      {r.explanation?.validated && r.explanation.text && (
        <section className="explain glass">
          <div className="lab">Plain-language rewrite · local model ({r.explanation.model}) · the engine summary above is authoritative</div>
          <p>{r.explanation.text}</p>
        </section>
      )}

      <section>
        <h3>Evidence ({evidence.length})</h3>
        {evidence.length === 0 && <p className="muted">No findings in the checks that completed.</p>}
        {evidence.map((e) => (
          <details key={e.id} className="ev glass">
            <summary>
              <span className={"sev sev-" + e.severity}>{e.severity}</span>
              <span className="claim">{e.claim}</span>
              <span className="muted src">{e.source?.name} · {e.verified ? "verified" : "unverified"} · {Math.round((e.confidence ?? 0) * 100)}%</span>
            </summary>
            <div className="evbody">
              <p className="muted">Check: <span className="mono">{e.id}</span> · fetched {e.source ? fmt(e.source.fetched_at) : "n/a"}</p>
              <pre>{JSON.stringify(e.data, null, 2)}</pre>
            </div>
          </details>
        ))}
      </section>

      <div className="cols">
        <section className="glass pad">
          <h3>Coverage</h3>
          <ul className="plain">{coverage.map((c) => (
            <li key={c.check} className={"st-" + c.status}><b>{c.check}</b> · {c.source ?? "n/a"} · {c.status}{c.detail ? " (" + c.detail + ")" : ""}</li>
          ))}</ul>
        </section>
        <section className="glass pad">
          <h3>Experimental ML signal</h3>
          <p className="muted">Status: <b>{r.model?.status ?? "unavailable"}</b>{r.model?.reason ? " · " + r.model.reason : ""}</p>
          {scoreOk ? <p>Model score: <b>{r.model.score}</b> <span className="muted">(experimental)</span></p> : <p className="muted">No score is shown because the backend did not provide a valid one.</p>}
        </section>
      </div>

      {(r.consequences ?? []).length > 0 && (
        <section className="glass pad"><h3>What it could mean</h3><ul className="plain">{r.consequences.map((c) => <li key={c}>{c}</li>)}</ul></section>
      )}
      <section className="glass pad"><h3>Limitations</h3><ul className="plain">{limits.map((l) => <li key={l} className="muted">{l}</li>)}</ul></section>
      <section className="glass pad"><h3>Data sources</h3><ul className="plain">{sources.map((s) => <li key={s.name + s.fetched_at}><b>{s.name}</b> <span className="muted">· {fmt(s.fetched_at)}</span></li>)}</ul></section>
    </article>
  );
}