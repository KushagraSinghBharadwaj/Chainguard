import { Link } from "react-router-dom";
import RiskBadge, { LEVEL_NOTE } from "../components/report/RiskBadge";
import type { RiskLevel } from "../types/report";
import "./info.css";

const LEVELS: RiskLevel[] = ["LOW", "MODERATE", "HIGH", "CRITICAL", "INSUFFICIENT_DATA"];

export default function About() {
  return (
    <section className="wrap info">
      <span className="chip">About</span>
      <h1>Security screening that shows its work</h1>
      <p className="lead">ChainGuard is a read-only security screening tool for Ethereum. You give it a wallet address, a token contract or a transaction, and it returns a risk level backed by evidence you can open and check. It never asks for private keys, never signs and never moves funds.</p>

      <h2>What it checks</h2>
      <div className="grid3">
        <div className="glass abt-card"><h3>Wallets</h3><p>Reviews an address's history and age, whether it carries delegated code, activity patterns, and links to addresses on sanctions or scam lists.</p></div>
        <div className="glass abt-card"><h3>Token contracts</h3><p>Reads owner powers (mint, pause, blacklist, ownership transfer), proxy and upgrade status, and token facts reported by GoPlus.</p></div>
        <div className="glass abt-card"><h3>Transactions</h3><p>Decodes calldata and flags dangerous permissions, such as an unlimited token approval, before you approve anything. Each check streams back live.</p></div>
      </div>

      <h2>How a risk level is decided</h2>
      <div className="glass abt-card">
        <p>The level comes from deterministic rules applied to evidence fetched from real data sources. Each finding carries a severity, a confidence, a verified flag, its source and the time it was fetched. No language model and no machine-learning model sets the level.</p>
        <ul className="levels" style={{ marginTop: 18, paddingLeft: 0 }}>
          {LEVELS.map((l) => <li key={l}><RiskBadge level={l} /><span>{LEVEL_NOTE[l]}</span></li>)}
        </ul>
      </div>

      <h2>The two optional AI layers</h2>
      <div className="grid2">
        <div className="glass abt-card"><h3>Experimental ML signal</h3><p>A gradient-boosting model is trained on labelled addresses. Its stored metrics are currently not clearly better than chance, so ChainGuard marks it "not reliable" and shows no score. It can never change the level.</p></div>
        <div className="glass abt-card"><h3>Plain-language rewrite</h3><p>For moderate-or-higher wallet and token reports, a local model (Ollama) rewrites the engine summary in simpler words. The text is validated against strict rules, labelled as a rewrite, and dropped if it fails. It never changes the level.</p></div>
      </div>

      <h2>Where the data comes from</h2>
      <div className="grid3">
        <div className="glass abt-card"><h3>Chain data</h3><ul><li>Alchemy: bytecode and delegated code</li><li>Etherscan: history, first transaction, verified ABI</li></ul></div>
        <div className="glass abt-card"><h3>Threat intelligence</h3><ul><li>GoPlus: address and token flags</li><li>OFAC SDN sanctions list</li><li>ScamSniffer community list</li></ul></div>
        <div className="glass abt-card"><h3>A caveat</h3><p>GoPlus lists ScamSniffer among its own sources, so those two are not fully independent evidence. Every report says so.</p></div>
      </div>

      <h2>How the pieces fit</h2>
      <div className="glass abt-card">
        <div className="flow">
          <span className="node">Website or Chrome extension</span><span className="arr">→</span>
          <span className="node">FastAPI backend</span><span className="arr">→</span>
          <span className="node">Data providers + PostgreSQL</span><span className="arr">→</span>
          <span className="node">Rules engine</span><span className="arr">→</span>
          <span className="node">Evidence report</span><span className="arr">→</span>
          <span className="node">Optional local rewrite</span>
        </div>
        <p style={{ marginTop: 16 }}>The Chrome extension can screen transactions that a page asks your wallet to send and show the result in an overlay. It talks to the same backend as this site.</p>
      </div>

      <h2>Privacy and safety</h2>
      <div className="grid2">
        <div className="glass abt-card"><h3>Read-only by design</h3><p>ChainGuard only reads public blockchain data. It has no wallet connection, no key access and no ability to send a transaction.</p></div>
        <div className="glass abt-card"><h3>Anonymous client</h3><p>Your browser gets a random client token so your history stays separate. The shared report cache contains no user identity.</p></div>
      </div>

      <h2>Honest limitations</h2>
      <div className="glass callout">
        <h3>Not a guarantee</h3>
        <p>Not appearing on a list does not mean an address is safe, and a high finding does not prove a scam. Community lists lag behind new scams, large wallets can be only partly analysed, and ChainGuard screens addresses, contracts and transactions, not the content of a website.</p>
      </div>
      <div className="cta"><Link className="btn primary" to="/scan">Start Security Scan →</Link><Link className="btn ghost" to="/docs">Read the documentation</Link></div>
    </section>
  );
}