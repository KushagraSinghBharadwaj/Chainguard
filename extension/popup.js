// Website address used by the "open on website" links. Change this when the site is deployed.
const SITE = "http://localhost:5173";
const API = "http://127.0.0.1:8000/v1/";
const $ = (id) => document.getElementById(id);
const ADDR = /^0x[0-9a-fA-F]{40}$/;
const DATA = /^0x([0-9a-fA-F]{2})*$/;
const LEVELS = ["LOW", "MODERATE", "HIGH", "CRITICAL"];
const RANK = { critical: 4, high: 3, medium: 2, moderate: 2, low: 1, info: 0 };
const NOTE = {
  LOW: "No findings in the checks that completed. This is not a guarantee of safety.",
  MODERATE: "Some warning signs. Read the findings before you trust this.",
  HIGH: "Serious warning signs. Do not interact unless you fully understand and trust this.",
  CRITICAL: "Strong evidence of danger. Do not interact with this.",
  INSUFFICIENT_DATA: "Not enough data to judge. Unknown is not safe.",
};

const MODES = {
  wallets: { label: "Wallet address", button: "Analyze wallet" },
  tokens: { label: "Token contract address", button: "Analyze token" },
  transactions: { label: "Contract being called (to)", button: "Analyze transaction" },
};

// Real, public Ethereum mainnet addresses. The transaction sample is real calldata
// (unlimited USDT approval to Uniswap Permit2) but it is not a broadcast transaction.
const PERMIT2 = "0x000000000022D473030F116dDEE9F6B43aC78BA3";
const USDT = "0xdAC17F958D2ee523a2206206994597C13D831ec7";
const SAMPLES = {
  wallets: { addr: "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045" },
  tokens: { addr: USDT },
  transactions: {
    addr: USDT,
    data: "0x095ea7b3" + PERMIT2.slice(2).toLowerCase().padStart(64, "0") + "f".repeat(64),
  },
};

let mode = "wallets";

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = String(text);
  return n;
}
const shorten = (s) => (s.length > 18 ? s.slice(0, 8) + "\u2026" + s.slice(-6) : s);

function setMsg(text, isErr) {
  const m = $("msg");
  m.textContent = text || "";
  m.className = "msg" + (isErr ? " err" : "");
}

document.querySelectorAll("[data-site]").forEach((a) => {
  a.href = SITE + a.dataset.site;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
});

/* ---------- sliding tab highlight ---------- */
function placeInk() {
  const a = document.querySelector(".tab.active");
  const ink = $("ink");
  if (!a) return;
  ink.style.width = a.offsetWidth + "px";
  ink.style.transform = "translateX(" + a.offsetLeft + "px)";
}
requestAnimationFrame(placeInk);
window.addEventListener("load", placeInk);

/* ---------- connection token ---------- */
function setTokenState() {
  const has = $("token").value.trim().length > 0;
  $("connState").textContent = has ? "Connected" : "No token";
  $("connState").className = "pill" + (has ? " ok" : "");
}
chrome.storage.local.get("token", (r) => {
  if (r.token) $("token").value = r.token;
  else $("conn").open = true;
  setTokenState();
});
$("token").addEventListener("input", () => {
  chrome.storage.local.set({ token: $("token").value.trim() });
  setTokenState();
});
$("register").addEventListener("click", async () => {
  setMsg("Creating a token\u2026");
  try {
    const res = await fetch(API + "clients/register", { method: "POST" });
    if (!res.ok) throw new Error(res.status);
    const j = await res.json();
    $("token").value = j.token;
    chrome.storage.local.set({ token: j.token });
    setTokenState();
    $("conn").open = false;
    setMsg("New token saved in this browser.");
  } catch (e) {
    setMsg("Could not create a token. Check that the backend is running on port 8000.", true);
  }
});

/* ---------- wallet guard strip (last transaction screened on a page) ---------- */
function renderGuard(log) {
  const box = $("guard");
  box.replaceChildren();
  const lvl = log.length ? String(log[0].level || "").toLowerCase() : "";
  box.className = "guard fx tilt rise " + lvl;
  const head = el("div", "ghead");
  head.append(el("span", "gdot"), el("b", "", "Wallet guard"),
    el("span", "gsub", log.length ? "MetaMask & other wallets \u00b7 " + log.length + " screened" : "MetaMask & other wallets"));
  box.append(head);
  if (!log.length) {
    box.append(el("p", "gnone", "Nothing screened yet. When a site asks your wallet to send a transaction, ChainGuard shows its risk on the page before you confirm."));
    return;
  }
  const e = log[0];
  const last = el("div", "glast");
  const row = el("div", "grow");
  row.append(el("span", "chip", String(e.level || "").replace(/_/g, " ")), el("span", "gw", e.wallet || "Wallet"),
    el("span", "mono dim", shorten(String(e.to || ""))), el("span", "gsub", e.at ? new Date(e.at).toLocaleTimeString() : ""));
  last.append(row);
  (e.top || []).slice(0, 2).forEach((c) => last.append(el("div", "gclaim", c)));
  box.append(last);
}
chrome.storage.local.get("guardLog", (r) => renderGuard(Array.isArray(r.guardLog) ? r.guardLog : []));
chrome.storage.onChanged.addListener((c, area) => {
  if (area === "local" && c.guardLog) renderGuard(c.guardLog.newValue || []);
});

/* ---------- tabs ---------- */
document.querySelectorAll(".tab").forEach((b) =>
  b.addEventListener("click", () => {
    mode = b.dataset.mode;
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === b));
    placeInk();
    const isHist = mode === "history";
    const isDocs = mode === "docs";
    $("form").hidden = isHist || isDocs;
    $("hist").hidden = !isHist;
    $("docs").hidden = !isDocs;
    $("out").replaceChildren();
    setMsg("");
    if (isHist) { loadHistory(); return; }
    if (isDocs) return;
    $("addrLabel").textContent = MODES[mode].label;
    $("go").textContent = MODES[mode].button;
    $("dataRow").hidden = mode !== "transactions";
  })
);

$("sample").addEventListener("click", () => {
  const s = SAMPLES[mode];
  $("addr").value = s.addr;
  $("calldata").value = s.data || "";
  setMsg(mode === "transactions"
    ? "Loaded: unlimited USDT approval to Uniswap Permit2 (real contracts, example calldata)."
    : "Loaded a real mainnet address.");
});

/* ---------- result ---------- */
function render(r) {
  const level = String(r.risk_level || "UNKNOWN").toUpperCase();
  const idx = LEVELS.indexOf(level);
  const box = el("div", "result");

  const v = el("div", "verdict fx tilt rise " + level.toLowerCase());
  const head = el("div", "vhead");
  head.append(el("span", "", "Risk level"), el("span", "", r.engine_version || ""));
  v.append(head, el("div", "vlevel", level.replace(/_/g, " ")));
  if (NOTE[level]) v.append(el("div", "vnote", NOTE[level]));
  const meter = el("div", "meter");
  LEVELS.forEach((_, i) => {
    const seg = el("i", i <= idx ? "on" : "");
    seg.style.setProperty("--k", i);
    meter.append(seg);
  });
  v.append(meter);
  if (r.summary) v.append(el("p", "vsum", r.summary));
  const cov = r.coverage || [];
  if (cov.length) {
    const done = cov.filter((c) => c.status === "completed").length;
    v.append(el("div", "coverage", done + " of " + cov.length + " checks completed"));
  }
  if (r.subject && r.subject.key) v.append(el("div", "subject mono", (r.subject.type || "") + " \u00b7 " + r.subject.key));
  box.append(v);

  const ev = (r.evidence || []).slice().sort((a, b) =>
    (RANK[String(b.severity).toLowerCase()] || 0) - (RANK[String(a.severity).toLowerCase()] || 0));
  const s1 = el("div", "sect fx rise");
  s1.style.setProperty("--i", 1);
  s1.append(el("h2", "", "Why this level (" + ev.length + ")"));
  if (!ev.length) s1.append(el("p", "", "Nothing found by the checks that completed."));
  ev.forEach((e, n) => {
    const sev = String(e.severity || "info").toLowerCase();
    const row = el("div", "ev fx rise " + sev);
    row.style.setProperty("--i", n + 2);
    const text = el("div");
    text.append(el("p", "", e.claim || e.id || ""));
    const bits = [];
    if (e.source && e.source.name) bits.push("source: " + e.source.name);
    bits.push(e.verified ? "verified" : "unverified");
    text.append(el("small", "", bits.join(" \u00b7 ")));
    row.append(el("span", "chip " + sev, sev), text);
    s1.append(row);
  });
  box.append(s1);

  const cons = (r.consequences || [])
    .map((c) => (typeof c === "string" ? c : c.summary || c.claim || c.description || ""))
    .filter(Boolean);
  if (cons.length) {
    const s = el("div", "sect fx rise");
    s.append(el("h2", "", "What could happen"));
    cons.forEach((c) => s.append(el("p", "", c)));
    box.append(s);
  }

  const lim = r.limitations || [];
  if (lim.length) {
    const s = el("div", "sect fx");
    const d = el("details", "lim");
    d.append(el("summary", "", "Limitations (" + lim.length + ")"));
    const ul = el("ul");
    lim.forEach((l) => ul.append(el("li", "", l)));
    d.append(ul);
    s.append(d);
    box.append(s);
  }

  const srcs = r.data_sources || [];
  if (srcs.length) {
    const s = el("div", "sect fx");
    s.append(el("h2", "", "Data sources"));
    const w = el("div", "src");
    srcs.forEach((d) => {
      const t = d.fetched_at ? new Date(d.fetched_at).toLocaleString() : "";
      w.append(el("span", "", d.name + (t ? " \u00b7 " + t : "")));
    });
    s.append(w);
    box.append(s);
  }

  const cta = el("a", "btn primary fx", "Full report & PDF download on the website \u2197");
  cta.href = SITE + "/scan";
  cta.target = "_blank";
  cta.rel = "noopener noreferrer";
  box.append(cta);
  box.append(el("div", "foot", "Screening result, not a guarantee of safety. ChainGuard never signs or sends transactions."));
  $("out").replaceChildren(box);
}

$("go").addEventListener("click", async () => {
  const token = $("token").value.trim();
  const addr = $("addr").value.trim();
  const out = $("out");
  if (!token) { $("conn").open = true; return setMsg("Add a client token under Connection, or create one.", true); }
  if (!ADDR.test(addr)) return setMsg("Enter a valid 0x address (42 characters).", true);

  let body = { chain_id: 1, address: addr };
  if (mode === "transactions") {
    const data = $("calldata").value.trim() || "0x";
    if (!DATA.test(data)) return setMsg("Calldata must be hex starting with 0x.", true);
    body = { chain_id: 1, to: addr, data };
  }

  setMsg("");
  $("go").disabled = true;
  $("go").textContent = "Analyzing\u2026";
  try {
    const res = await fetch(API + mode + "/analyze", {
      method: "POST",
      headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (res.status === 401) { out.replaceChildren(); $("conn").open = true; return setMsg("Token rejected. Create a new token under Connection.", true); }
    if (res.status === 429) { out.replaceChildren(); return setMsg("Rate limit reached. Wait a moment and try again.", true); }
    if (!res.ok) { out.replaceChildren(); return setMsg("The backend rejected the request (" + res.status + ").", true); }
    render(await res.json());
  } catch (e) {
    out.replaceChildren();
    setMsg("Could not reach the backend. Start it on port 8000.", true);
  } finally {
    $("go").disabled = false;
    $("go").textContent = MODES[mode].button;
  }
});

/* ---------- history ---------- */
const TYPE_TAB = { wallet: "wallets", token: "tokens", transaction: "transactions" };

async function loadHistory() {
  const box = $("hist");
  const token = $("token").value.trim();
  if (!token) {
    $("conn").open = true;
    return box.replaceChildren(el("p", "msg err", "Add a client token under Connection first."));
  }
  box.replaceChildren(el("p", "msg", "Loading history\u2026"));
  try {
    const res = await fetch(API + "history?limit=20", { headers: { Authorization: "Bearer " + token } });
    if (!res.ok) {
      const t = res.status === 401 ? "Token rejected. Create a new token under Connection." : "Could not load history (" + res.status + ").";
      return box.replaceChildren(el("p", "msg err", t));
    }
    const items = (await res.json()).items || [];
    if (!items.length) {
      return box.replaceChildren(el("p", "msg", "No checks yet. Analyze a wallet, token or transaction and it will appear here."));
    }
    const list = el("div", "hlist");
    items.forEach((i, n) => {
      const lvl = String(i.risk_level || "").toLowerCase();
      const row = el("button", "hrow fx rise " + lvl);
      row.style.setProperty("--i", Math.min(n, 8));
      row.type = "button";
      const mid = el("span", "hmid");
      mid.append(el("b", "", i.subject_type), el("span", "mono", shorten(String(i.subject_key))));
      row.append(el("span", "chip " + lvl, lvl.replace(/_/g, " ")), mid,
        el("span", "hwhen", new Date(i.created_at).toLocaleString()));
      if (i.subject_type !== "transaction" && ADDR.test(i.subject_key)) {
        row.addEventListener("click", () => {
          document.querySelector('.tab[data-mode="' + TYPE_TAB[i.subject_type] + '"]').click();
          $("addr").value = i.subject_key;
        });
      }
      list.append(row);
    });
    const more = el("a", "btn ghost fx wide", "Open full history & PDFs on the website \u2197");
    more.href = SITE + "/history";
    more.target = "_blank";
    more.rel = "noopener noreferrer";
    box.replaceChildren(list, more);
  } catch (e) {
    box.replaceChildren(el("p", "msg err", "Could not reach the backend. Start it on port 8000."));
  }
}

/* ---------- hover motion: logo look-at, ambient glow, tilt, spotlight, magnetic buttons, ripple ---------- */
if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  const root = document.documentElement;
  let raf = 0, ev = null, active = null;
  const clear = (n) => ["--tx", "--ty", "--rx", "--ry"].forEach((p) => n.style.removeProperty(p));
  const frame = () => {
    raf = 0;
    if (!ev) return;
    root.style.setProperty("--gx", ev.clientX + "px");
    root.style.setProperty("--gy", ev.clientY + "px");
    const logo = $("logo"), lb = logo.getBoundingClientRect();
    const dx = ev.clientX - (lb.left + lb.width / 2), dy = ev.clientY - (lb.top + lb.height / 2);
    const d = Math.hypot(dx, dy) || 1, k = Math.min(1, d / 200);
    logo.style.setProperty("--lx", ((dx / d) * k).toFixed(3));
    logo.style.setProperty("--ly", ((dy / d) * k).toFixed(3));
    const t = ev.target && ev.target.closest ? ev.target.closest(".fx") : null;
    if (active && active !== t) clear(active);
    active = t;
    if (!t) return;
    const b = t.getBoundingClientRect();
    const x = ev.clientX - b.left, y = ev.clientY - b.top, nx = x / b.width - 0.5, ny = y / b.height - 0.5;
    t.style.setProperty("--mx", x + "px");
    t.style.setProperty("--my", y + "px");
    if (t.classList.contains("btn")) {
      t.style.setProperty("--tx", (nx * 10).toFixed(1) + "px");
      t.style.setProperty("--ty", (ny * 8).toFixed(1) + "px");
    } else if (t.classList.contains("tilt")) {
      t.style.setProperty("--rx", (-ny * 6).toFixed(2) + "deg");
      t.style.setProperty("--ry", (nx * 8).toFixed(2) + "deg");
    }
  };
  document.addEventListener("pointermove", (e) => { ev = e; if (!raf) raf = requestAnimationFrame(frame); }, { passive: true });
  root.addEventListener("pointerleave", () => {
    if (active) clear(active);
    active = null;
    $("logo").style.setProperty("--lx", "0");
    $("logo").style.setProperty("--ly", "0");
  });
  document.addEventListener("click", (e) => {
    const t = e.target && e.target.closest ? e.target.closest(".btn, .tab") : null;
    if (!t || t.disabled) return;
    const b = t.getBoundingClientRect(), s = Math.max(b.width, b.height) * 2.2;
    const r = document.createElement("span");
    r.className = "ripple";
    r.style.cssText = "left:" + (e.clientX - b.left) + "px;top:" + (e.clientY - b.top) + "px;width:" + s + "px;height:" + s + "px";
    t.appendChild(r);
    r.addEventListener("animationend", () => r.remove());
  });
}