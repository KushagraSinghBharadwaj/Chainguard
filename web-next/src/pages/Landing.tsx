import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { prefersReduced } from "../motion/useReducedMotion";
import "./landing.css";

gsap.registerPlugin(ScrollTrigger);

const CARDS = [
  ["◈", "Wallet Check", "Review an address: history, delegated code and listed-address links.", "/scan/wallet"],
  ["◉", "Token Check", "Inspect owner powers, proxy status and token facts.", "/scan/token"],
  ["⇄", "Transaction Check", "Decode calldata and flag dangerous permissions before approval.", "/scan/transaction"],
  ["⛨", "Extension Screening", "The Chrome extension can screen wallet requests as you make them.", "/extension"],
] as const;
const STEPS = [
  ["1", "Input", "Paste a wallet, token contract or transaction."],
  ["2", "Analyze", "Deterministic checks run against live sources. Each reports what completed and what was partial."],
  ["3", "Read the evidence", "Every finding links to its source and timestamp. Limitations stay visible."],
] as const;

export default function Landing() {
  const root = useRef<HTMLDivElement>(null);
  const stage = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (prefersReduced() || !root.current) return;
    const ctx = gsap.context(() => {
      gsap.utils.toArray<HTMLElement>("[data-reveal]").forEach((el) =>
        gsap.from(el, { y: 36, opacity: 0, duration: 0.9, ease: "power3.out", scrollTrigger: { trigger: el, start: "top 88%", once: true } }));
    }, root);
    return () => ctx.revert();
  }, []);

  const onMove = (e: React.PointerEvent) => {
    if (prefersReduced() || !stage.current) return;
    const b = stage.current.getBoundingClientRect();
    stage.current.style.setProperty("--px", String(((e.clientX - b.left) / b.width - 0.5) * 2));
    stage.current.style.setProperty("--py", String(((e.clientY - b.top) / b.height - 0.5) * 2));
  };
  const d = (n: number) => ({ "--d": n } as React.CSSProperties);

  return (
    <div ref={root} className="landing">
      <section className="wrap hero">
        <div className="hero-copy">
          <span className="chip">Read-only · Ethereum mainnet</span>
          <h1>Your Assets.<br />Your Intelligence.<br /><span className="grad">Your Security.</span></h1>
          <p className="lead">An intelligent security layer for Web3. Detect threats, understand permissions and evaluate blockchain activity before you interact.</p>
          <div className="cta">
            <Link className="btn primary" to="/scan">Start Security Scan →</Link>
            <button className="btn ghost" onClick={() => document.getElementById("how")?.scrollIntoView({ behavior: prefersReduced() ? "auto" : "smooth" })}>Explore ChainGuard</button>
          </div>
        </div>

        <div className="stage" ref={stage} onPointerMove={onMove} aria-hidden="true">
          <div className="ring r1 layer" style={d(6)} /><div className="ring r2 layer" style={d(10)} /><div className="ring r3 layer" style={d(14)} />
          <svg className="shield layer" style={d(22)} viewBox="0 0 200 220">
            <defs>
              <linearGradient id="sg" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#8757ff" stopOpacity=".9" /><stop offset="1" stopColor="#42b8ff" stopOpacity=".55" /></linearGradient>
              <filter id="gl"><feGaussianBlur stdDeviation="6" /></filter>
            </defs>
            <path d="M100 10 180 40v65c0 45-35 75-80 95-45-20-80-50-80-95V40z" fill="url(#sg)" filter="url(#gl)" opacity=".55" />
            <path d="M100 10 180 40v65c0 45-35 75-80 95-45-20-80-50-80-95V40z" fill="rgba(9,11,22,.55)" stroke="url(#sg)" strokeWidth="2.5" />
            <g stroke="#70e7ff" strokeWidth="1.5" fill="none" opacity=".9"><path d="M100 70v30M100 100 72 128M100 100l28 28" /><circle cx="100" cy="66" r="7" /><circle cx="70" cy="132" r="7" /><circle cx="130" cy="132" r="7" /></g>
          </svg>
          <div className="note glass n1 layer" style={d(30)}><b>Evidence-linked</b><span>Every finding cites its source</span></div>
          <div className="note glass n2 layer" style={d(38)}><b>Limitations shown</b><span>Partial checks are labelled</span></div>
          <div className="note glass n3 layer" style={d(26)}><b>Deterministic level</b><span>A language model never sets it</span></div>
        </div>
      </section>

      <section className="wrap cards">
        {CARDS.map(([ic, t, p, to]) => (
          <Link key={t} to={to} className="card glass" data-reveal>
            <span className="ic">{ic}</span><h3>{t}</h3><p>{p}</p><span className="go">Open →</span>
          </Link>
        ))}
      </section>

      <section id="how" className="wrap how">
        <span className="chip" data-reveal>How it works</span>
        <h2 data-reveal>Screening in three steps</h2>
        <ol className="steps">
          {STEPS.map(([n, t, p]) => (
            <li key={n} className="glass" data-reveal><span className="num">{n}</span><h3>{t}</h3><p>{p}</p></li>
          ))}
        </ol>
      </section>

      <section className="wrap honest" data-reveal>
        <div className="glass">
          <h3>What a result does and does not mean</h3>
          <p>A low level means no findings in the checks that completed, not that an address is safe. A high level is a finding to investigate, not a verdict that something is a scam. Optional plain-language text is a rewrite of the engine summary and never changes the level.</p>
        </div>
      </section>
    </div>
  );
}