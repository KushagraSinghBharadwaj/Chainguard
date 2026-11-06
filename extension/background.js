const API = "http://127.0.0.1:8000/v1/";
const ADDR = /^0x[0-9a-fA-F]{40}$/;
const DATA = /^0x([0-9a-fA-F]{2})*$/;

chrome.runtime.onMessage.addListener((msg, _sender, send) => {
  if (!msg || msg.type !== "analyze") return;

  (async () => {
    const tx = msg.tx || {};
    if (!ADDR.test(tx.to || "") || !DATA.test(tx.data || "") || tx.data.length > 20000) {
      return send({ ok: false, error: "The transaction request could not be read." });
    }
    if (!Number.isInteger(msg.chainId)) {
      return send({ ok: false, error: "The wallet did not report which network this is on." });
    }
    const { token } = await chrome.storage.local.get("token");
    if (!token) {
      return send({ ok: false, error: "No client token. Open the ChainGuard popup and create one." });
    }
    try {
      const res = await fetch(API + "transactions/analyze", {
        method: "POST",
        headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
        body: JSON.stringify({ chain_id: msg.chainId, to: tx.to, data: tx.data }),
      });
      if (res.status === 401) return send({ ok: false, error: "Token rejected. Create a new token in the popup." });
      if (res.status === 429) return send({ ok: false, error: "Rate limit reached. Try again in a moment." });
      if (!res.ok) return send({ ok: false, error: "The backend returned " + res.status + "." });
      send({ ok: true, report: await res.json() });
    } catch (e) {
      send({ ok: false, error: "The ChainGuard backend is not reachable on port 8000." });
    }
  })();

  return true; // keep the channel open for the async reply
});
