const ADDR = /^0x[0-9a-fA-F]{40}$/;
const DATA = /^0x([0-9a-fA-F]{2})*$/;
const LEVELS = ["LOW", "MODERATE", "HIGH", "CRITICAL"];
const COLORS = { LOW: "#1c8f5a", MODERATE: "#c58a0a", HIGH: "#d4452f", CRITICAL: "#a3162a" };
const RANK = { critical: 4, high: 3, medium: 2, moderate: 2, low: 1, info: 0 };

const CSS = `
:host{all:initial}
.wrap{position:fixed;inset:0;z-index:2147483647;display:flex;align-items:flex-start;justify-content:flex-end;
  padding:18px;background:rgba(10,16,32,.35);font:13px/1.45 "Segoe UI",system-ui,sans-serif;color:#1a2238}
.card{width:380px;max-width:100%;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 18px 50px rgba(10,16,32,.4)}
.top{background:linear-gradient(135deg,#14213d,#1d2d52);color:#fff;padding:12px 16px;font-weight:650}
.top small{display:block;font-weight:400;color:#b8c3e0;font-size:11.5px}
.body{padding:14px 16px}
.lvl{border-left:5px solid var(--c,#7a859e);padding-left:12px}
.lvl b{display:block;font-size:24px;line-height:1.1;color:var(--c,#7a859e)}
.lvl span{font-size:11.5px;color:#667089}
.meter{display:flex;gap:4px;margin:10px 0}
.meter i{flex:1;height:6px;border-radius:3px;background:#e4e8f2}
.meter i.on{background:var(--c)}
p{margin:6px 0}
.to{font:12px Consolas,monospace;color:#41506f;word-break:break-all}
ul{margin:8px 0 0;padding-left:18px}li{margin-bottom:4px}
.err{color:#d4452f;font-weight:600}
.btns{display:flex;gap:8px;padding:0 16px 16px}
button{flex:1;font:inherit;font-weight:650;border-radius:8px;padding:10px;cursor:pointer}
.rej{border:0;background:#2f5bff;color:#fff}
.rej:hover{background:#2447d6}
.go{border:1px solid #d5dbea;background:#fff;color:#14213d}
.go:hover{background:#f4f6fb}
button:focus-visible{outline:2px solid #2f5bff;outline-offset:2px}
.foot{padding:0 16px 14px;font-size:11px;color:#667089}
`;

function node(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = String(text);
  return n;
}

function show(tx, result) {
  return new Promise((resolve) => {
    const host = document.createElement("div");
    const root = host.attachShadow({ mode: "closed" });
    const style = document.createElement("style");
    style.textContent = CSS;
    const wrap = node("div", "wrap");
    const card = node("div", "card");

    const top = node("div", "top", "ChainGuard");
    top.append(node("small", "", "Read-only check of the transaction your wallet is about to ask you to approve"));
    const body = node("div", "body");

    if (result.ok) {
      const r = result.report || {};
      const level = String(r.risk_level || "UNKNOWN").toUpperCase();
      const idx = LEVELS.indexOf(level);
      const lvl = node("div", "lvl");
      lvl.style.setProperty("--c", COLORS[level] || "#7a859e");
      lvl.append(node("span", "", "Risk level"), node("b", "", level.replace(/_/g, " ")));
      body.append(lvl);
      const meter = node("div", "meter");
      meter.style.setProperty("--c", COLORS[level] || "#7a859e");
      LEVELS.forEach((_, i) => meter.append(node("i", i <= idx ? "on" : "")));
      body.append(meter);
      if (r.summary) body.append(node("p", "", r.summary));
      const ev = (r.evidence || [])
        .slice()
        .sort((a, b) => (RANK[String(b.severity).toLowerCase()] || 0) - (RANK[String(a.severity).toLowerCase()] || 0))
        .slice(0, 3);
      if (ev.length) {
        const ul = node("ul");
        ev.forEach((e) => ul.append(node("li", "", e.claim || e.id || "")));
        body.append(ul);
      }
    } else {
      body.append(node("p", "err", "ChainGuard could not check this transaction."));
      body.append(node("p", "", result.error || "Unknown error."));
      body.append(node("p", "", "Nothing was checked. Unknown is not safe."));
    }
    body.append(node("p", "to", "Calls contract " + tx.to));

    const btns = node("div", "btns");
    const rej = node("button", "rej", "Reject");
    const go = node("button", "go", "Continue to wallet");
    btns.append(rej, go);
    const foot = node("div", "foot", "Continue only passes the request to your wallet, which still asks you to confirm. ChainGuard never signs or sends.");

    const done = (decision) => { host.remove(); document.removeEventListener("keydown", onKey, true); resolve(decision); };
    const onKey = (e) => { if (e.key === "Escape") done("reject"); };
    rej.addEventListener("click", () => done("reject"));
    go.addEventListener("click", () => done("continue"));
    document.addEventListener("keydown", onKey, true);

    card.append(top, body, btns, foot);
    wrap.append(card);
    root.append(style, wrap);
    (document.documentElement || document).append(host);
    rej.focus();
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

  queue = queue.then(async () => {
    const result = await new Promise((res) => {
      chrome.runtime.sendMessage({ type: "analyze", tx: { to: tx.to, data: tx.data }, chainId: d.chainId }, (r) => {
        if (chrome.runtime.lastError || !r) res({ ok: false, error: "The extension did not respond." });
        else res(r);
      });
    });
    const decision = await show(tx, result);
    reply(d.id, "decision", decision);
  });
});
