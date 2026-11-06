const API = "http://127.0.0.1:8000/v1/";
const $ = (id) => document.getElementById(id);
const ADDR = /^0x[0-9a-fA-F]{40}$/;
const DATA = /^0x([0-9a-fA-F]{2})*$/;
const LEVELS = ["LOW", "MODERATE", "HIGH", "CRITICAL"];

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

function setMsg(text, isErr) {
  const m = $("msg");
  m.textContent = text || "";
  m.className = "msg" + (isErr ? " err" : "");
}

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
  setMsg("Creating a token…");
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

document.querySelectorAll(".tab").forEach((b) =>
  b.addEventListener("click", () => {
    mode = b.dataset.mode;
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === b));
    const isHist = mode === "history";
    $("form").hidden = isHist;
    $("hist").hidden = !isHist;
    $("out").replaceChildren();
    setMsg("");
    if (isHist) { loadHistory(); return; }
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

function render(r) {
  const level = String(r.risk_level || "UNKNOWN").toUpperCase();
  const idx = LEVELS.indexOf(level);
  const box = el("div", "result");

  const v = el("div", "verdict" + (idx >= 0 ? " " + level.toLowerCase() : ""));
  const head = el("div", "vhead");
  head.append(el("span", "vlabel", "Risk level"), el("span", "vlabel", r.engine_version || ""));
  v.append(head, el("div", "vlevel", level.replace(/_/g, " ")));
  const meter = el("div", "meter");
  LEVELS.forEach((_, i) => meter.append(el("i", i <= idx ? "on" : "")));
  v.append(meter);
  if (r.summary) v.append(el("p", "vsum", r.summary));
  const cov = r.coverage || [];
  if (cov.length) {
    const done = cov.filter((c) => c.status === "completed").length;
    v.append(el("div", "coverage", done + " of " + cov.length + " checks completed"));
  }
  box.append(v);

  const ev = r.evidence || [];
  const s1 = el("div", "sect");
  s1.append(el("h2", "", "Evidence"));
  if (!ev.length) s1.append(el("p", "", "Nothing found by the checks that completed."));
  ev.forEach((e) => {
    const sev = String(e.severity || "info").toLowerCase();
    const row = el("div", "ev");
    row.append(el("span", "chip " + sev, sev), el("p", "", e.claim || e.id || ""));
    s1.append(row);
  });
  box.append(s1);

  const cons = (r.consequences || [])
    .map((c) => (typeof c === "string" ? c : c.summary || c.claim || c.description || ""))
    .filter(Boolean);
  if (cons.length) {
    const s = el("div", "sect");
    s.append(el("h2", "", "Possible consequences"));
    cons.forEach((c) => s.append(el("p", "", c)));
    box.append(s);
  }

  const lim = r.limitations || [];
  if (lim.length) {
    const s = el("div", "sect");
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
    const s = el("div", "sect");
    s.append(el("h2", "", "Data sources"));
    const w = el("div", "src");
    srcs.forEach((d) => {
      const t = d.fetched_at ? new Date(d.fetched_at).toLocaleString() : "";
      w.append(el("span", "", d.name + (t ? " · " + t : "")));
    });
    s.append(w);
    box.append(s);
  }

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
  $("go").textContent = "Analyzing…";
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

const TYPE_TAB = { wallet: "wallets", token: "tokens", transaction: "transactions" };
const shorten = (s) => (s.length > 18 ? s.slice(0, 8) + "…" + s.slice(-6) : s);

async function loadHistory() {
  const box = $("hist");
  const token = $("token").value.trim();
  if (!token) {
    $("conn").open = true;
    return box.replaceChildren(el("p", "msg err", "Add a client token under Connection first."));
  }
  box.replaceChildren(el("p", "msg", "Loading history…"));
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
    items.forEach((i) => {
      const row = el("button", "hrow");
      row.type = "button";
      const lvl = String(i.risk_level || "").toUpperCase();
      const mid = el("span", "hmid");
      mid.append(el("b", "", i.subject_type), el("span", "mono", shorten(String(i.subject_key))));
      row.append(el("span", "chip " + lvl.toLowerCase(), lvl.replace(/_/g, " ")), mid,
        el("span", "hwhen", new Date(i.created_at).toLocaleString()));
      if (i.subject_type !== "transaction" && ADDR.test(i.subject_key)) {
        row.addEventListener("click", () => {
          document.querySelector('.tab[data-mode="' + TYPE_TAB[i.subject_type] + '"]').click();
          $("addr").value = i.subject_key;
        });
      }
      list.append(row);
    });
    box.replaceChildren(list);
  } catch (e) {
    box.replaceChildren(el("p", "msg err", "Could not reach the backend. Start it on port 8000."));
  }
}
