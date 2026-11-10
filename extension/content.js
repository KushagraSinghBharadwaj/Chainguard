// Website address used by the "open on website" links. Change this when the site is deployed.
const SITE = "http://localhost:5173";
const ADDR = /^0x[0-9a-fA-F]{40}$/;
const DATA = /^0x([0-9a-fA-F]{2})*$/;
const LEVELS = ["LOW", "MODERATE", "HIGH", "CRITICAL"];
const COLORS = {
  LOW: "#4fe3c1", MODERATE: "#ffbd59", HIGH: "#ff7a45", CRITICAL: "#ff526b", INSUFFICIENT_DATA: "#8b92a8",
};
const NOTE = {
  LOW: "No findings in the checks that completed. This is not a guarantee of safety.",
  MODERATE: "Some warning signs. Read the findings before you continue.",
  HIGH: "Serious warning signs. Do not continue unless you fully understand and trust this.",
  CRITICAL: "Strong evidence of danger. Reject this request.",
  INSUFFICIENT_DATA: "Not enough data to judge. Unknown is not safe.",
};
const RANK = { critical: 4, high: 3, medium: 2, moderate: 2, low: 1, info: 0 };
const SEV_COLOR = { critical: "#ff526b", high: "#ff7a45", medium: "#ffbd59", moderate: "#ffbd59", low: "#4fe3c1", info: "#70e7ff" };
// Standard 4-byte selectors, looked up locally only to label the request.
const KNOWN = {
  "0x095ea7b3": "approve(address,uint256)",
  "0xa9059cbb": "transfer(address,uint256)",
  "0x23b872dd": "transferFrom(address,address,uint256)",
  "0xa22cb465": "setApprovalForAll(address,bool)",
  "0x39509351": "increaseAllowance(address,uint256)",
  "0xd505accf": "permit(address,address,uint256,uint256,uint8,bytes32,bytes32)",
};

const CSS = `
:host{all:initial}
*{box-sizing:border-box}
.wrap{position:fixed;inset:0;z-index:2147483647;display:flex;align-items:flex-start;justify-content:flex-end;padding:18px;
  background:rgba(3,4,10,.62);backdrop-filter:blur(3px);animation:fade .25s ease both;
  font:13px/1.5 "Inter",system-ui,-apple-system,"Segoe UI",sans-serif;color:#eef0fa}
.card{position:relative;width:470px;max-width:100%;max-height:calc(100vh - 36px);overflow:auto;background:#090b16;
  border:1px solid rgba(255,255,255,.12);border-radius:20px;
  box-shadow:0 30px 90px rgba(0,0,0,.75),0 0 0 1px rgba(135,87,255,.18);animation:pop .5s cubic-bezier(.22,1,.36,1) both}
.bar{display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid rgba(255,255,255,.08);
  background:linear-gradient(135deg,rgba(135,87,255,.22),rgba(66,184,255,.12));font-weight:700}
.brand{background:linear-gradient(120deg,#fff,#b9a4ff 55%,#70e7ff);-webkit-background-clip:text;background-clip:text;color:transparent;font-size:15px}
.link{position:relative;flex:1;height:2px;border-radius:2px;background:rgba(255,255,255,.14);overflow:hidden}
.link i{position:absolute;top:0;left:-30%;width:30%;height:100%;background:linear-gradient(90deg,transparent,#70e7ff,transparent);animation:flow 1.6s linear infinite}
.wal{padding:3px 10px;border-radius:999px;font-size:12px;border:1px solid rgba(112,231,255,.5);color:#70e7ff;background:rgba(112,231,255,.1)}
.sec{position:relative;padding:14px 16px;border-bottom:1px solid rgba(255,255,255,.06)}
.sec::after{content:"";position:absolute;inset:0;pointer-events:none;opacity:0;transition:opacity .3s;
  background:radial-gradient(240px circle at var(--mx,50%) var(--my,50%),rgba(112,231,255,.09),rgba(135,87,255,.06) 45%,transparent 70%)}
.sec:hover::after{opacity:1}
.h{font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:#98a0ba;font-weight:700;margin-bottom:8px}
.kv{display:flex;gap:10px;padding:2px 0}
.kv .k{width:84px;flex:none;color:#98a0ba}
.kv .v{flex:1;word-break:break-all}
.kv .v.mono{font-family:ui-monospace,"Cascadia Code",Consolas,monospace;font-size:12px;color:#70e7ff}
.dim{color:#98a0ba}
.row{display:flex;gap:8px;align-items:baseline;padding:3px 0;transition:transform .3s cubic-bezier(.22,1,.36,1)}
.row:hover{transform:translateX(4px)}
.row .g{width:14px;text-align:center;flex:none}
.row .t{flex:1}
.row .ms{color:#98a0ba;flex:none;font-size:11.5px}
.row.q{color:#5d6480}
.row.run .g{color:#42b8ff}
.row.ok .g{color:#4fe3c1}
.row.bad .g{color:#ffbd59}
.dots i{font-style:normal;opacity:.2;animation:blink 1.2s infinite}
.dots i:nth-child(2){animation-delay:.2s}
.dots i:nth-child(3){animation-delay:.4s}
.lvl{font-size:32px;font-weight:800;letter-spacing:-.02em;line-height:1.1;color:var(--c);text-shadow:0 0 30px var(--c)}
.note{font-weight:600;margin:4px 0 2px}
.meter{display:flex;gap:5px;margin:10px 0}
.meter i{flex:1;height:6px;border-radius:4px;background:rgba(255,255,255,.1);transform-origin:left}
.meter i.on{background:var(--c);animation:grow .6s cubic-bezier(.22,1,.36,1) both;animation-delay:calc(var(--k)*120ms + 200ms)}
.ev{display:flex;gap:10px;align-items:flex-start;padding:8px 10px;margin:4px -6px;border-radius:12px;border:1px solid transparent;
  transition:transform .3s cubic-bezier(.22,1,.36,1),border-color .3s,background .3s}
.ev:hover{transform:translateX(5px);border-color:var(--c);background:rgba(255,255,255,.04)}
.ev .chip{flex:none;margin-top:1px;padding:2px 9px;border-radius:999px;font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
  color:var(--c);border:1px solid var(--c);background:rgba(255,255,255,.04)}
.ev small{display:block;color:#98a0ba;font-size:11px}
.cons{margin:4px 0;color:#c4c9de}
.err{color:#ff526b;font-weight:700}
details{margin-top:10px;color:#98a0ba}
summary{cursor:pointer;color:#70e7ff;font-weight:600}
.cr{margin:4px 0;word-break:break-word}
.st{display:inline-block;min-width:84px}
.st.completed{color:#4fe3c1}.st.partial{color:#ffbd59}.st.unavailable{color:#ff526b}.st.skipped{color:#98a0ba}
a.site{display:inline-block;margin-top:10px;color:#70e7ff;font-weight:600;text-decoration:none;transition:transform .3s cubic-bezier(.22,1,.36,1)}
a.site:hover{transform:translateX(4px);text-decoration:underline}
.btns{display:flex;gap:10px;padding:14px 16px}
button{position:relative;overflow:hidden;flex:1;font:inherit;font-weight:700;border-radius:12px;padding:11px;cursor:pointer;
  transform:translate(var(--tx,0px),var(--ty,0px));transition:transform .35s cubic-bezier(.22,1,.36,1),box-shadow .35s,border-color .3s,scale .15s}
button:hover:not(:disabled){transform:translate(var(--tx,0px),calc(var(--ty,0px) - 2px))}
button:active:not(:disabled){scale:.95}
.rej{border:0;color:#fff;background:linear-gradient(135deg,#9a72ff,#5e8bff)}
.rej:hover{box-shadow:0 14px 40px -8px rgba(135,87,255,.9)}
.go{border:1px solid rgba(255,255,255,.18);background:rgba(255,255,255,.04);color:#eef0fa}
.go:hover:not(:disabled){border-color:rgba(112,231,255,.6)}
.go.danger{border-color:#ff526b;color:#ff526b}
.go.danger:hover:not(:disabled){box-shadow:0 12px 34px -10px rgba(255,82,107,.8)}
.go:disabled{opacity:.35;cursor:not-allowed}
button:focus-visible{outline:2px solid #b9a4ff;outline-offset:2px}
.rp{position:absolute;border-radius:50%;pointer-events:none;background:rgba(255,255,255,.35);transform:translate(-50%,-50%) scale(0);animation:rip .65s cubic-bezier(.22,1,.36,1) forwards}
.foot{padding:0 16px 14px;font-size:11px;color:#6b7390}
@keyframes fade{from{opacity:0}to{opacity:1}}
@keyframes pop{from{opacity:0;transform:translateY(-14px) scale(.97)}to{opacity:1;transform:none}}
@keyframes flow{to{left:100%}}
@keyframes blink{0%,80%,100%{opacity:.2}40%{opacity:1}}
@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@keyframes rip{to{transform:translate(-50%,-50%) scale(1);opacity:0}}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}.dots i{opacity:1}}
`;

function node(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = String(text);
  return n;
}

function dots() {
  const d = node("span", "dots");
  for (let i = 0; i < 3; i++) d.append(node("i", "", "."));
  return d;
}

function kv(k, v, cls) {
  const r = node("div", "kv");
  r.append(node("span", "k", k), node("span", "v" + (cls ? " " + cls : ""), v));
  return r;
}

function describe(data) {
  if (!data || data === "0x") return { selector: "0x", name: "plain transfer, no call data" };
  const sel = data.slice(0, 10).toLowerCase();
  return { selector: sel, name: KNOWN[sel] || "unrecognised function" };
}

function formatValue(v) {
  try {
    const w = BigInt(v || "0x0");
    if (w === 0n) return null;
    const eth = Number(w) / 1e18;
    return (eth < 0.0001 ? "<0.0001" : eth.toFixed(4)) + " ETH";
  } catch (e) { return null; }
}

function makeRow(label) {
  const row = node("div", "row q");
  const g = node("span", "g", "\u00b7");
  const t = node("span", "t", label);
  const tail = node("span", "tail");
  t.append(tail);
  const ms = node("span", "ms", "");
  row.append(g, t, ms);
  return { row, g, tail, ms };
}

function setState(rec, state, ms) {
  rec.row.className = "row " + state;
  rec.tail.textContent = "";
  rec.ms.textContent = typeof ms === "number" ? ms + " ms" : "";
  if (state === "run") {
    rec.g.textContent = ">";
    rec.tail.append(node("span", "dim", " running"), dots());
  } else if (state === "ok") {
    rec.g.textContent = "\u2713";
  } else if (state === "bad") {
    rec.g.textContent = "!";
    rec.tail.append(node("span", "dim", " unavailable"));
  }
}

// Keep a short local log so the popup can show the last transaction ChainGuard screened.
function remember(tx, wallet, r, level) {
  try {
    const top = (r.evidence || []).slice()
      .sort((a, b) => (RANK[String(b.severity).toLowerCase()] || 0) - (RANK[String(a.severity).toLowerCase()] || 0))
      .slice(0, 2).map((e) => String(e.claim || e.id || "").slice(0, 160));
    chrome.storage.local.get("guardLog", (g) => {
      const log = Array.isArray(g.guardLog) ? g.guardLog : [];
      log.unshift({ wallet, to: tx.to, level, top, at: Date.now() });
      chrome.storage.local.set({ guardLog: log.slice(0, 10) });
    });
  } catch (e) { /* storage unavailable */ }
}

function show(tx, chainId, wallet) {
  return new Promise((resolve) => {
    const host = document.createElement("div");
    const root = host.attachShadow({ mode: "closed" });
    const style = document.createElement("style");
    style.textContent = CSS;
    const wrap = node("div", "wrap");
    const card = node("div", "card");

    const bar = node("div", "bar");
    const link = node("span", "link");
    link.append(node("i"));
    bar.append(node("span", "brand", "ChainGuard"), link, node("span", "wal", wallet));

    const ask = node("div", "sec");
    const info = describe(tx.data);
    ask.append(node("div", "h", "Your wallet is about to ask you to approve"));
    ask.append(kv("Wallet", wallet));
    ask.append(kv("Site", window.location.hostname || "unknown"));
    ask.append(kv("Network", chainId === 1 ? "Ethereum mainnet" : "chain " + chainId));
    ask.append(kv("Action", info.name + " (" + info.selector + ")"));
    ask.append(kv("Third party", tx.to, "mono"));
    const val = formatValue(tx.value);
    if (val) ask.append(kv("Value", val));
    ask.append(node("div", "dim", "Action name comes from a local list of standard selectors. The backend decodes the full call."));

    const checks = node("div", "sec");
    checks.append(node("div", "h", "Live checks"));
    const list = node("div");
    checks.append(list);

    const verdict = node("div", "sec");
    verdict.hidden = true;

    const btns = node("div", "btns");
    const rej = node("button", "rej", "Reject");
    const go = node("button", "go", "Continue to wallet");
    go.disabled = true;
    btns.append(rej, go);
    const foot = node("div", "foot",
      "Continue only passes the request to " + wallet + ", which still asks you to confirm. ChainGuard never signs or sends.");

    const recs = new Map();
    let boot = makeRow("connect to the backend");
    setState(boot, "run");
    list.append(boot.row);
    let finished = false;
    let port = null;

    const dropBoot = () => { if (boot) { boot.row.remove(); boot = null; } };
    const ensure = (id, label) => {
      let r = recs.get(id);
      if (!r) { r = makeRow(label || id); recs.set(id, r); list.append(r.row); }
      return r;
    };
    const finish = () => {
      finished = true;
      dropBoot();
      go.disabled = false;
      if (port) { try { port.disconnect(); } catch (e) { /* already closed */ } }
    };

    function siteLink() {
      const a = node("a", "site", "Full report, history and PDF download on the ChainGuard website \u2197");
      a.href = SITE + "/scan";
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      return a;
    }

    function showError(message) {
      verdict.hidden = false;
      verdict.append(
        node("div", "err", "ChainGuard could not check this transaction."),
        node("div", "", message || "Unknown error."),
        node("div", "dim", "Nothing was checked. Unknown is not safe.")
      );
    }

    function showReport(r) {
      const level = String(r.risk_level || "UNKNOWN").toUpperCase();
      const color = COLORS[level] || "#8b92a8";
      verdict.style.setProperty("--c", color);
      verdict.hidden = false;
      verdict.append(node("div", "h", "Verdict"));
      verdict.append(node("div", "lvl", level.replace(/_/g, " ")));
      if (NOTE[level]) verdict.append(node("div", "note", NOTE[level]));
      const idx = LEVELS.indexOf(level);
      const meter = node("div", "meter");
      LEVELS.forEach((_, i) => {
        const seg = node("i", i <= idx ? "on" : "");
        seg.style.setProperty("--k", i);
        meter.append(seg);
      });
      verdict.append(meter);
      if (r.summary) verdict.append(node("div", "", r.summary));
      if (idx >= 2) { go.textContent = "Continue anyway"; go.classList.add("danger"); }

      const ev = (r.evidence || []).slice()
        .sort((a, b) => (RANK[String(b.severity).toLowerCase()] || 0) - (RANK[String(a.severity).toLowerCase()] || 0));
      if (ev.length) {
        verdict.append(node("div", "h", "Why (" + ev.length + " findings)"));
        ev.slice(0, 6).forEach((e) => {
          const sev = String(e.severity || "info").toLowerCase();
          const row = node("div", "ev");
          row.style.setProperty("--c", SEV_COLOR[sev] || "#70e7ff");
          const body = node("div");
          body.append(node("div", "", e.claim || e.id || ""));
          const bits = [];
          if (e.source && e.source.name) bits.push("source: " + e.source.name);
          bits.push(e.verified ? "verified" : "unverified");
          body.append(node("small", "", bits.join(" \u00b7 ")));
          row.append(node("span", "chip", sev), body);
          verdict.append(row);
        });
        if (ev.length > 6) verdict.append(node("div", "dim", "+" + (ev.length - 6) + " more findings on the website."));
      }

      const cons = (r.consequences || [])
        .map((c) => (typeof c === "string" ? c : c.summary || c.claim || c.description || ""))
        .filter(Boolean);
      if (cons.length) {
        verdict.append(node("div", "h", "What could happen"));
        cons.slice(0, 4).forEach((c) => verdict.append(node("div", "cons", "\u2022 " + c)));
      }

      const cov = Array.isArray(r.coverage) ? r.coverage : [];
      if (cov.length) {
        const done = cov.filter((c) => c.status === "completed").length;
        const det = node("details");
        det.append(node("summary", "", "checks: " + done + " of " + cov.length + " completed"));
        cov.forEach((c) => {
          const row = node("div", "cr");
          const st = String(c.status || "");
          row.append(node("span", "st " + st, st), node("span", "", c.check || ""));
          if (c.source) row.append(node("span", "dim", "  via " + c.source));
          if (c.detail) row.append(node("div", "dim", "  " + c.detail));
          det.append(row);
        });
        const srcs = (Array.isArray(r.data_sources) ? r.data_sources : [])
          .map((s) => {
            const t = s && s.fetched_at ? new Date(s.fetched_at) : null;
            return (s && s.name ? s.name : "?") + (t && !isNaN(t) ? " @ " + t.toLocaleString() : "");
          })
          .join(" | ");
        if (srcs) det.append(node("div", "cr dim", "sources: " + srcs));
        verdict.append(det);
      }
      verdict.append(siteLink());
      remember(tx, wallet, r, level);
    }

    function handle(m) {
      if (!m || finished) return;
      if (m.event === "start") {
        dropBoot();
        (m.steps || []).forEach((s) => ensure(s.id, s.label));
      } else if (m.event === "step") {
        dropBoot();
        const r = ensure(m.id);
        setState(r, m.status === "running" ? "run" : m.status === "done" ? "ok" : "bad", m.ms);
      } else if (m.event === "report") {
        finish();
        showReport(m.report || {});
      } else if (m.event === "error") {
        finish();
        showError(m.message);
      }
    }

    const done = (decision) => {
      host.remove();
      document.removeEventListener("keydown", onKey, true);
      if (port && !finished) { try { port.disconnect(); } catch (e) { /* already closed */ } }
      resolve(decision);
    };
    const onKey = (e) => { if (e.key === "Escape") done("reject"); };
    rej.addEventListener("click", () => done("reject"));
    go.addEventListener("click", () => { if (!go.disabled) done("continue"); });
    document.addEventListener("keydown", onKey, true);

    // Hover motion: section spotlight, magnetic buttons and click ripple.
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      card.addEventListener("pointermove", (e) => {
        const path = e.composedPath();
        const sec = path.find((n) => n.classList && n.classList.contains("sec"));
        if (sec) {
          const b = sec.getBoundingClientRect();
          sec.style.setProperty("--mx", e.clientX - b.left + "px");
          sec.style.setProperty("--my", e.clientY - b.top + "px");
        }
        [rej, go].forEach((btn) => {
          if (path.includes(btn)) {
            const b = btn.getBoundingClientRect();
            btn.style.setProperty("--tx", (((e.clientX - b.left) / b.width - 0.5) * 10).toFixed(1) + "px");
            btn.style.setProperty("--ty", (((e.clientY - b.top) / b.height - 0.5) * 8).toFixed(1) + "px");
          } else {
            btn.style.removeProperty("--tx");
            btn.style.removeProperty("--ty");
          }
        });
      });
      card.addEventListener("pointerleave", () => [rej, go].forEach((b) => { b.style.removeProperty("--tx"); b.style.removeProperty("--ty"); }));
      [rej, go].forEach((btn) => btn.addEventListener("click", (e) => {
        if (btn.disabled) return;
        const b = btn.getBoundingClientRect(), s = Math.max(b.width, b.height) * 2.2;
        const r = node("span", "rp");
        r.style.cssText = "left:" + (e.clientX - b.left) + "px;top:" + (e.clientY - b.top) + "px;width:" + s + "px;height:" + s + "px";
        btn.append(r);
      }));
    }

    card.append(bar, ask, checks, verdict, btns, foot);
    wrap.append(card);
    root.append(style, wrap);
    (document.documentElement || document).append(host);
    rej.focus();

    try {
      port = chrome.runtime.connect({ name: "chainguard-analyze" });
      port.onMessage.addListener(handle);
      port.onDisconnect.addListener(() => {
        void chrome.runtime.lastError;
        if (!finished) { finish(); showError("The extension stopped responding."); }
      });
      port.postMessage({ tx: { to: tx.to, data: tx.data }, chainId });
    } catch (e) {
      finish();
      showError("The extension did not respond.");
    }
  });
}

function reply(id, type, decision) {
  window.postMessage({ source: "chainguard-content", id, type, decision }, window.location.origin);
}

let queue = Promise.resolve();

window.addEventListener("message", (ev) => {
  if (ev.source !== window) return;
  const d = ev.data;
  if (!d || d.source !== "chainguard-inpage" || typeof d.id !== "number") return;
  reply(d.id, "ack");

  const tx = d.tx || {};
  const valid = ADDR.test(tx.to || "") && DATA.test(tx.data || "") && tx.data.length <= 20000;
  if (!valid) { reply(d.id, "decision", "continue"); return; }
  const wallet = typeof d.wallet === "string" && d.wallet ? d.wallet.slice(0, 40) : "Wallet";

  queue = queue
    .then(async () => {
      const decision = await show(tx, d.chainId, wallet);
      reply(d.id, "decision", decision);
    })
    .catch((e) => {
      // ChainGuard is advisory: if its own overlay breaks, the wallet request must not hang.
      console.warn("[ChainGuard] overlay failed, passing the request to the wallet.", e);
      reply(d.id, "decision", "continue");
    });
});