const ADDR = /^0x[0-9a-fA-F]{40}$/;
const DATA = /^0x([0-9a-fA-F]{2})*$/;
const LEVELS = ["LOW", "MODERATE", "HIGH", "CRITICAL"];
const COLORS = {
  LOW: "#5fd38d", MODERATE: "#e5c07b", HIGH: "#f14c4c", CRITICAL: "#ff3b6b", INSUFFICIENT_DATA: "#9cdcfe",
};
const RANK = { critical: 4, high: 3, medium: 2, moderate: 2, low: 1, info: 0 };
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
.wrap{position:fixed;inset:0;z-index:2147483647;display:flex;align-items:flex-start;justify-content:flex-end;
  padding:18px;background:rgba(0,0,0,.55);
  font:12.5px/1.5 "Cascadia Code","Cascadia Mono",Consolas,"SF Mono",Menlo,monospace;color:#d4d4d4}
.card{width:440px;max-width:100%;max-height:calc(100vh - 36px);overflow:auto;background:#0a0a0f;
  border:1px solid #23232e;border-radius:10px;box-shadow:0 20px 60px rgba(0,0,0,.7)}
.bar{display:flex;align-items:center;gap:8px;padding:9px 14px;border-bottom:1px solid #23232e;
  background:#0d0d14;color:#808080;font-size:11.5px}
.bar b{color:#c586c0;font-weight:600}
.bar .dot{width:9px;height:9px;border-radius:50%;background:#569cd6;display:inline-block}
.sec{padding:12px 14px;border-bottom:1px solid #16161e}
.c{color:#6a9955}.k{color:#c586c0}.n{color:#569cd6}.s{color:#9cdcfe}.dim{color:#808080}
.addr{word-break:break-all;color:#9cdcfe}
.row{display:flex;gap:8px;align-items:baseline;padding:2px 0}
.row .g{width:14px;text-align:center;flex:none}
.row .t{flex:1}
.row .ms{color:#808080;flex:none}
.row.q{color:#555}
.row.run .g{color:#569cd6}
.row.ok .g{color:#5fd38d}
.row.bad .g{color:#e5c07b}
.dots i{font-style:normal;opacity:.2;animation:blink 1.2s infinite}
.dots i:nth-child(2){animation-delay:.2s}
.dots i:nth-child(3){animation-delay:.4s}
@keyframes blink{0%,80%,100%{opacity:.2}40%{opacity:1}}
@media (prefers-reduced-motion:reduce){.dots i{animation:none;opacity:1}}
.lvl b{display:block;font-size:26px;line-height:1.15;color:var(--c)}
.meter{display:flex;gap:4px;margin:8px 0}
.meter i{flex:1;height:5px;border-radius:3px;background:#23232e}
.meter i.on{background:var(--c)}
.ev{margin:3px 0}
.ev .sv{display:inline-block;min-width:64px;color:#569cd6}
.err{color:#f14c4c;font-weight:600}
details{margin-top:10px;color:#808080}
summary{cursor:pointer;color:#569cd6}
.cr{margin:4px 0;word-break:break-word}
.st{display:inline-block;min-width:84px}
.st.completed{color:#5fd38d}.st.partial{color:#e5c07b}.st.unavailable{color:#f14c4c}.st.skipped{color:#808080}
.btns{display:flex;gap:8px;padding:12px 14px}
button{flex:1;font:inherit;font-weight:600;border-radius:6px;padding:9px;cursor:pointer}
.rej{border:0;background:#569cd6;color:#0a0a0f}
.rej:hover{background:#6aa8e0}
.go{border:1px solid #3a3a4a;background:transparent;color:#d4d4d4}
.go:hover:not(:disabled){background:#16161e}
.go:disabled{opacity:.35;cursor:not-allowed}
button:focus-visible{outline:2px solid #c586c0;outline-offset:2px}
.foot{padding:0 14px 12px;font-size:11px;color:#6b6b78}
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

function describe(data) {
  if (!data || data === "0x") return { selector: "0x", name: "plain transfer, no call data" };
  const sel = data.slice(0, 10).toLowerCase();
  return { selector: sel, name: KNOWN[sel] || "unrecognised function" };
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

function show(tx, chainId) {
  return new Promise((resolve) => {
    const host = document.createElement("div");
    const root = host.attachShadow({ mode: "closed" });
    const style = document.createElement("style");
    style.textContent = CSS;
    const wrap = node("div", "wrap");
    const card = node("div", "card");

    const bar = node("div", "bar");
    bar.append(node("span", "dot"), node("b", "", "chainguard"), node("span", "", "// read-only"));

    const ask = node("div", "sec");
    const info = describe(tx.data);
    const l1 = node("div");
    l1.append(node("span", "k", "call "), node("span", "n", info.selector + " "), node("span", "s", info.name));
    const l2 = node("div");
    l2.append(node("span", "k", "to   "), node("span", "addr", tx.to));
    ask.append(
      node("div", "c", "// your wallet is about to ask you to approve:"), l1, l2,
      node("div", "dim", "(name from a local list of standard selectors; the backend decodes the full call)")
    );

    const checks = node("div", "sec");
    checks.append(node("div", "c", "// live checks"));
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
      "Continue only passes the request to your wallet, which still asks you to confirm. ChainGuard never signs or sends.");

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
      const color = COLORS[level] || "#808080";
      verdict.style.setProperty("--c", color);
      verdict.hidden = false;
      verdict.append(node("div", "c", "// verdict"));
      const lvl = node("div", "lvl");
      lvl.append(node("b", "", level.replace(/_/g, " ")));
      verdict.append(lvl);
      const idx = LEVELS.indexOf(level);
      const meter = node("div", "meter");
      LEVELS.forEach((_, i) => meter.append(node("i", i <= idx ? "on" : "")));
      verdict.append(meter);
      if (r.summary) verdict.append(node("div", "", r.summary));
      (r.evidence || [])
        .slice()
        .sort((a, b) => (RANK[String(b.severity).toLowerCase()] || 0) - (RANK[String(a.severity).toLowerCase()] || 0))
        .slice(0, 3)
        .forEach((e) => {
          const row = node("div", "ev");
          row.append(node("span", "sv", String(e.severity || "info")), node("span", "", e.claim || e.id || ""));
          verdict.append(row);
        });
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

  queue = queue
    .then(async () => {
      const decision = await show(tx, d.chainId);
      reply(d.id, "decision", decision);
    })
    .catch((e) => {
      // ChainGuard is advisory: if its own overlay breaks, the wallet request must not hang.
      console.warn("[ChainGuard] overlay failed, passing the request to the wallet.", e);
      reply(d.id, "decision", "continue");
    });
});