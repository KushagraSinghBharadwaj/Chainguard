import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { analyzeAddress } from "../services/analyze";
import { chainName, useWallet } from "../wallet/WalletContext";
import "./info.css";
import "./wallet.css";

const INSTALL: [string, string][] = [
  ["MetaMask", "https://metamask.io/download/"],
  ["Rabby", "https://rabby.io/"],
  ["Coinbase Wallet", "https://www.coinbase.com/wallet/downloads"],
  ["Trust Wallet", "https://trustwallet.com/browser-extension"],
];

export default function Wallet() {
  const { wallets, conn, busyId, error, connect, disconnect, switchToMainnet, getBalance } = useWallet();
  const nav = useNavigate();
  const [bal, setBal] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanErr, setScanErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let live = true;
    setBal(null);
    getBalance().then((b) => { if (live) setBal(b); });
    return () => { live = false; };
  }, [getBalance]);

  const scan = async () => {
    if (!conn) return;
    setScanning(true);
    setScanErr(null);
    try {
      const r = await analyzeAddress(conn.address);
      nav("/report/" + r.report_id);
    } catch (e) {
      setScanErr(e instanceof Error ? e.message : "The scan failed. Check that the backend is running.");
    } finally {
      setScanning(false);
    }
  };

  const copy = async () => {
    if (!conn) return;
    try { await navigator.clipboard.writeText(conn.address); setCopied(true); window.setTimeout(() => setCopied(false), 1500); } catch { /* clipboard blocked */ }
  };

  return (
    <section className="wrap info">
      <span className="chip">Wallet</span>
      <h1>{conn ? "Your connected wallet" : "Connect your wallet"}</h1>
      <p className="lead">
        Connecting shares only your public address and the network you are on. ChainGuard never asks for a signature, never sends a transaction and never sees your keys or seed phrase.
      </p>

      {!conn && (
        <>
          <h2>Wallets found in this browser</h2>
          {wallets.length === 0 ? (
            <div className="glass abt-card">
              <h3>No wallet detected</h3>
              <p>Install a browser wallet extension, then refresh this page.</p>
              <ul>{INSTALL.map(([n, u]) => <li key={n}><a href={u} target="_blank" rel="noopener noreferrer">{n} &#x2197;</a></li>)}</ul>
            </div>
          ) : (
            <div className="wal-list">
              {wallets.map((w) => (
                <div key={w.id} className="wal-item">
                  {w.icon ? <img className="wal-icon" src={w.icon} alt="" /> : <span className="wal-icon" />}
                  <div className="wal-name">{w.name}<small>Browser extension wallet</small></div>
                  <button type="button" className="btn primary" disabled={busyId !== null} onClick={() => connect(w)}>
                    {busyId === w.id ? "Check your wallet\u2026" : "Connect"}
                  </button>
                </div>
              ))}
            </div>
          )}
          {error && <p className="wal-err">{error}</p>}
          <p className="muted wal-note">
            Supported now: Ethereum wallets that run as a browser extension (MetaMask, Rabby, Coinbase Wallet, Trust Wallet). Mobile wallets through WalletConnect and Solana wallets such as Glow are not supported yet.
          </p>
        </>
      )}

      {conn && (
        <div className="glass wal-card">
          <div className="wal-row">
            <span className="k">Wallet</span>
            <span className="wal-who">
              {conn.icon ? <img className="wal-icon sm" src={conn.icon} alt="" /> : null}
              <b>{conn.name}</b>
            </span>
          </div>
          <div className="wal-row">
            <span className="k">Address</span>
            <span className="wal-addr">{conn.address} <button type="button" className="btn ghost sm" onClick={copy}>{copied ? "Copied" : "Copy"}</button></span>
          </div>
          <div className="wal-row">
            <span className="k">Network</span>
            <span>
              {chainName(conn.chainId)}
              {conn.chainId !== 1 && (
                <span className="wal-warn">
                  ChainGuard analyses Ethereum mainnet data. Testnet addresses have almost no history there.{" "}
                  <button type="button" className="btn ghost sm" onClick={switchToMainnet}>Switch to Ethereum Mainnet</button>
                </span>
              )}
            </span>
          </div>
          <div className="wal-row"><span className="k">Balance</span><span>{bal === null ? "\u2026" : bal + " ETH"}</span></div>
          <div className="cta">
            <button type="button" className="btn primary" disabled={scanning} onClick={scan}>{scanning ? "Scanning\u2026" : "Scan this wallet \u2192"}</button>
            <button type="button" className="btn ghost" onClick={disconnect}>Disconnect</button>
          </div>
          {scanErr && <p className="wal-err">{scanErr}</p>}
          {error && <p className="wal-err">{error}</p>}
        </div>
      )}
    </section>
  );
}