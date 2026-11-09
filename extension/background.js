const API = "http://127.0.0.1:8000/v1/";
const ADDR = /^0x[0-9a-fA-F]{40}$/;
const DATA = /^0x([0-9a-fA-F]{2})*$/;
const TIMEOUT_MS = 30000;

const failure = (message) => ({ event: "error", message });

// The overlay opens a long-lived port and receives one message per backend event.
chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "chainguard-analyze") return;
  const ctrl = new AbortController();
  const state = { closed: false, timedOut: false, started: false };
  const send = (m) => {
    if (state.closed) return;
    try { port.postMessage(m); } catch (e) { state.closed = true; }
  };
  port.onDisconnect.addListener(() => { state.closed = true; ctrl.abort(); });
  port.onMessage.addListener((msg) => {
    if (state.started) return;
    state.started = true;
    analyze(msg, send, ctrl, state);
  });
});

async function readLines(body, onObject) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (value) buf += decoder.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (!line) continue;
      try { onObject(JSON.parse(line)); } catch (e) { /* skip a malformed line */ }
    }
    if (done) break;
  }
}

async function analyze(msg, send, ctrl, state) {
  const tx = (msg && msg.tx) || {};
  if (!ADDR.test(tx.to || "") || !DATA.test(tx.data || "") || tx.data.length > 20000) {
    return send(failure("The transaction request could not be read."));
  }
  if (!Number.isInteger(msg.chainId)) {
    return send(failure("The wallet did not report which network this is on."));
  }
  const { token } = await chrome.storage.local.get("token");
  if (!token) return send(failure("No client token. Open the ChainGuard popup and create one."));

  const timer = setTimeout(() => { state.timedOut = true; ctrl.abort(); }, TIMEOUT_MS);
  const init = () => ({
    method: "POST",
    headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
    body: JSON.stringify({ chain_id: msg.chainId, to: tx.to, data: tx.data }),
    signal: ctrl.signal,
  });
  let terminal = false;
  try {
    let res = await fetch(API + "transactions/analyze/stream", init());
    if (res.status === 404 || res.status === 405) {
      // Older backend without the stream endpoint: use the single-report endpoint.
      res = await fetch(API + "transactions/analyze", init());
      if (res.ok) return send({ event: "report", report: await res.json() });
    }
    if (res.status === 401) return send(failure("Token rejected. Create a new token in the popup."));
    if (res.status === 429) return send(failure("Rate limit reached. Try again in a moment."));
    if (!res.ok || !res.body) return send(failure("The backend returned " + res.status + "."));
    await readLines(res.body, (obj) => {
      if (obj.event === "report" || obj.event === "error") terminal = true;
      send(obj);
    });
    if (!terminal) send(failure("The analysis ended before it produced a result."));
  } catch (e) {
    if (state.timedOut) send(failure("The check took longer than 30 seconds and was stopped."));
    else if (!state.closed) send(failure("The ChainGuard backend is not reachable on port 8000."));
  } finally {
    clearTimeout(timer);
  }
}