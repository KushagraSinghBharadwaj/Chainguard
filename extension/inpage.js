// Runs in the page's own context so it can wrap window.ethereum.
// It only pauses an eth_sendTransaction request while ChainGuard shows its result,
// then hands the original request to the wallet unchanged. It never signs or sends.
(() => {
  if (window.__chainguardInpage) return;
  window.__chainguardInpage = true;

  const wrapped = new WeakSet();
  const pending = new Map();
  let seq = 0;

  window.addEventListener("message", (ev) => {
    if (ev.source !== window) return;
    const d = ev.data;
    if (!d || d.source !== "chainguard-content") return;
    const p = pending.get(d.id);
    if (!p) return;
    if (d.type === "ack") { clearTimeout(p.timer); return; }
    pending.delete(d.id);
    p.resolve(d.decision === "reject" ? "reject" : "continue");
  });

  // If the extension does not answer within 1.5 s, the request goes to the wallet
  // untouched. ChainGuard is advisory, so it must never block a wallet by failing.
  function screen(tx, chainId) {
    return new Promise((resolve) => {
      const id = ++seq;
      const timer = setTimeout(() => {
        pending.delete(id);
        console.warn("[ChainGuard] no response, passing the request to the wallet unchecked.");
        resolve("continue");
      }, 1500);
      pending.set(id, { resolve, timer });
      window.postMessage({ source: "chainguard-inpage", id, tx, chainId }, window.location.origin);
    });
  }

  function wrap(provider) {
    if (!provider || typeof provider.request !== "function" || wrapped.has(provider)) return;
    wrapped.add(provider);
    const orig = provider.request.bind(provider);
    try {
      provider.request = async function (args) {
        const tx = args && args.method === "eth_sendTransaction" && args.params && args.params[0];
        if (tx && tx.to) {
          let chainId = null;
          try { chainId = parseInt(await orig({ method: "eth_chainId" }), 16); } catch (e) {}
          const decision = await screen(
            { to: tx.to, data: tx.data || tx.input || "0x", value: tx.value || "0x0" },
            chainId
          );
          if (decision === "reject") {
            const err = new Error("User rejected the request.");
            err.code = 4001; // standard "user rejected" code
            throw err;
          }
        }
        return orig(args);
      };
    } catch (e) {
      console.warn("[ChainGuard] could not wrap this wallet provider.", e);
    }
  }

  function scan() {
    wrap(window.ethereum);
    if (window.ethereum && Array.isArray(window.ethereum.providers)) window.ethereum.providers.forEach(wrap);
  }

  window.addEventListener("eip6963:announceProvider", (e) => wrap(e.detail && e.detail.provider));
  window.addEventListener("ethereum#initialized", scan);
  const ask = () => window.dispatchEvent(new Event("eip6963:requestProvider"));
  scan(); ask();
  document.addEventListener("DOMContentLoaded", () => { scan(); ask(); });
  let n = 0;
  const iv = setInterval(() => { scan(); if (++n > 50) clearInterval(iv); }, 200);
})();
