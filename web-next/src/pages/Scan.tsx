import { useEffect, useState } from "react";
import { NavLink, useParams, useSearchParams } from "react-router-dom";
import { ETH_ADDRESS } from "../services/analyze";
import { useScan } from "../hooks/useScan";
import ScanTimeline from "../components/scan/ScanTimeline";
import ReportView from "../components/report/ReportView";
import "./scan.css";

const MODES = [
  ["wallet", "Wallet Scan", "Wallet address"],
  ["token", "Token Scan", "Token contract address"],
  ["transaction", "Transaction Scan", "Destination contract address"],
] as const;
type Mode = (typeof MODES)[number][0];
const CALLDATA = /^0x([0-9a-fA-F]{2})*$/;

export default function Scan() {
  const { mode: p } = useParams();
  const mode: Mode = MODES.find((m) => m[0] === p)?.[0] ?? "wallet";
  const label = MODES.find((m) => m[0] === mode)![2];
  const [sp] = useSearchParams();
  const [addr, setAddr] = useState(sp.get("address") ?? "");
  const [data, setData] = useState("0x");
  const [fieldErr, setFieldErr] = useState("");
  const scan = useScan();
  const { reset } = scan;

  useEffect(() => { reset(); setFieldErr(""); }, [mode, reset]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const a = addr.trim(), d = data.trim();
    if (!ETH_ADDRESS.test(a)) return setFieldErr("Enter a 42-character Ethereum address that starts with 0x.");
    if (mode === "transaction" && !CALLDATA.test(d)) return setFieldErr("Calldata must be even-length hex that starts with 0x.");
    setFieldErr("");
    if (mode === "transaction") void scan.runTx(a, d); else void scan.runAddress(a);
  };

  const t = scan.report?.detected_address_type;
  const mismatch = (mode === "wallet" && t === "contract") ? "That address is a contract, so the token analysis is shown."
    : (mode === "token" && t === "eoa") ? "That address is a wallet, so the wallet analysis is shown." : "";
  const busy = scan.phase === "running";

  return (
    <section className="wrap scan">
      <h1>Security Scan</h1>
      <p className="muted">Read-only screening on Ethereum mainnet. Nothing is signed or sent.</p>
      <nav className="tabs glass" aria-label="Scan type">
        {MODES.map(([m, name]) => <NavLink key={m} to={"/scan/" + m} className={({ isActive }) => (isActive || (!p && m === "wallet") ? "active" : "")}>{name}</NavLink>)}
      </nav>

      <form className="glass panel" onSubmit={submit} noValidate>
        <div className="field">
          <label htmlFor="addr">{label}</label>
          <input id="addr" className="mono" value={addr} onChange={(e) => setAddr(e.target.value)} placeholder="0x…" autoComplete="off" spellCheck={false} aria-invalid={!!fieldErr} aria-describedby="fe" />
        </div>
        {mode === "transaction" && (
          <div className="field">
            <label htmlFor="data">Transaction calldata</label>
            <textarea id="data" className="mono" rows={3} value={data} onChange={(e) => setData(e.target.value)} spellCheck={false} />
          </div>
        )}
        <p id="fe" className="err" role="alert">{fieldErr}</p>
        <div className="row">
          <button className="btn primary" disabled={busy} type="submit">{busy ? "Analyzing…" : "Analyze"}</button>
          {busy && <button type="button" className="btn ghost" onClick={reset}>Cancel</button>}
        </div>
      </form>

      {scan.phase !== "idle" && <ScanTimeline steps={scan.steps} live={scan.live} elapsed={scan.elapsed} log={scan.log} />}
      {scan.phase === "error" && <p className="err box" role="alert">{scan.error}</p>}
      {mismatch && <p className="notice">{mismatch}</p>}
      {scan.report && <ReportView r={scan.report} />}
    </section>
  );
}