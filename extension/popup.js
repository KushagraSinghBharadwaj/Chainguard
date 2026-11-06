const API = "http://127.0.0.1:8000/v1/";
const $ = (id) => document.getElementById(id);

chrome.storage.local.get("token", (r) => { if (r.token) $("token").value = r.token; });

function esc(s) {
  const d = document.createElement("div");
  d.textContent = String(s ?? "");
  return d.innerHTML;
}

$("go").addEventListener("click", async () => {
  const token = $("token").value.trim();
  const address = $("addr").value.trim();
  const out = $("out");
  if (!/^0x[0-9a-fA-F]{40}$/.test(address)) { out.textContent = "Enter a valid 0x address."; return; }
  if (!token) { out.textContent = "Enter your client token."; return; }
  chrome.storage.local.set({ token });
  out.textContent = "Analyzing...";
  try {
    const res = await fetch(API + $("kind").value + "/analyze", {
      method: "POST",
      headers: { "Authorization": "Bearer " + token, "Content-Type": "application/json" },
      body: JSON.stringify({ chain_id: 1, address }),
    });
    if (!res.ok) { out.textContent = "Request failed (" + res.status + ")."; return; }
    const r = await res.json();
    const ev = (r.evidence || []).map((e) =>
      "<li>" + esc(e.claim) + " <span class='sev'>[" + esc(e.severity) + "]</span></li>").join("");
    const lim = (r.limitations || []).map((l) => "<li>" + esc(l) + "</li>").join("");
    out.innerHTML =
      "<div class='lvl'>Level: " + esc(r.risk_level) + "</div>" +
      "<b>Evidence</b><ul>" + (ev || "<li>None found by completed checks.</li>") + "</ul>" +
      "<b>Limitations</b><ul>" + lim + "</ul>" +
      "<small>Not a guarantee of safety.</small>";
  } catch (e) {
    out.textContent = "Could not reach the backend. Is it running on port 8000?";
  }
});
