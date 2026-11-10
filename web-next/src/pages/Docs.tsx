import { useMemo } from "react";
import { Link } from "react-router-dom";
import { allReports } from "../services/reportCache";
import DownloadPdfButton from "../components/report/DownloadPdfButton";
import RiskBadge from "../components/report/RiskBadge";
import "./info.css";

const STEPS: [string, string, string][] = [
  ["Input and validation", "The address must be 0x plus 40 hex characters. Transaction calldata must be even-length hex. Invalid input is rejected before any request is sent.", "Subject, type, chain, generation time and engine version."],
  ["Address type detection", "For a plain address search, the backend reads the account's bytecode to decide whether it is a wallet or a contract, then runs the matching analysis.", "The detected type (wallet or contract)."],
  ["Data collection", "Providers are queried: Alchemy, Etherscan, GoPlus, plus the stored OFAC and ScamSniffer lists. Each check reports completed, partial or skipped.", "A Checks performed list with the source and status of every check."],
  ["Deterministic rules", "Rules turn the collected data into findings. Each has a severity, confidence, verified flag, source and fetch time.", "Every finding with its source, timestamp and raw data."],
  ["Risk level", "The engine assigns LOW, MODERATE, HIGH, CRITICAL or INSUFFICIENT DATA. Nothing else can change it.", "The level and its plain note, including that LOW is not a guarantee."],
  ["Experimental ML", "A model signal is shown only when the backend supplies a valid score. Currently it is marked not reliable.", "The ML status and the reason a score is or is not shown."],
  ["Plain-language rewrite", "For moderate-or-higher wallet and token reports, a local model may rewrite the summary. It is validated and labelled.", "The rewrite, labelled as a rewrite, only when it passed validation."],
  ["Limitations and sources", "Every report lists what could not be checked and which sources contributed, with timestamps.", "All limitations and data sources with fetch times."],
];

export default function Docs() {
  const reports = useMemo(() => allReports(), []);
  return (
    <section className="wrap info">
      <span className="chip">Documentation</span>
      <h1>How an analysis works, and your PDF record of it</h1>
      <p className="lead">Every scan produces a security analysis report you can download as a PDF in one click. The PDF documents each step below for that specific scan.</p>

      <h2>Get a PDF in one step</h2>
      <div className="glass abt-card">
        <p>Run a scan, then press <b>Download PDF report</b> at the top of the result. The file is built in your browser from the report you are looking at, and nothing is uploaded.</p>
        <div className="cta"><Link className="btn primary" to="/scan">Run a scan →</Link></div>
      </div>

      <h2>The eight steps and what the PDF records</h2>
      <div className="doc-steps">
        {STEPS.map(([t, what, pdf], i) => (
          <article key={t} className="glass doc-step">
            <span className="num">{i + 1}</span>
            <h3>{t}</h3>
            <p>{what}</p>
            <p className="pdf"><b>In the PDF:</b> {pdf}</p>
          </article>
        ))}
      </div>

      <h2>Download your reports</h2>
      {reports.length === 0 ? (
        <p className="muted">No reports are stored in this browser yet. <Link to="/scan">Run a scan</Link> and it will appear here.</p>
      ) : (
        <div className="rep-list">
          {reports.map((r) => (
            <div key={r.report_id} className="glass rep-row">
              <RiskBadge level={r.risk_level} />
              <div className="meta2"><span className="mono">{r.subject.key}</span><span className="muted">{r.subject.type} · {new Date(r.generated_at).toLocaleString()}</span></div>
              <div className="acts"><Link className="btn ghost sm" to={"/report/" + r.report_id}>Open</Link><DownloadPdfButton report={r} small label="Download PDF" /></div>
            </div>
          ))}
        </div>
      )}
      <p className="muted" style={{ marginTop: 14, fontSize: 13 }}>Only reports stored in this browser can be turned into a PDF, because the server's history list holds summaries, not full evidence.</p>

      <h2>What the PDF is not</h2>
      <div className="glass callout">
        <h3>A record, not a safety certificate</h3>
        <p>The PDF documents what ChainGuard checked and found for one address, contract or transaction at one moment. It is not a certificate of safety, and it does not scan the content of a website.</p>
      </div>
    </section>
  );
}