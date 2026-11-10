/* eslint-disable @typescript-eslint/no-explicit-any */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

// Minimal EIP-1193 provider. ChainGuard only ever calls read-only methods plus the standard
// connect request. It never asks a wallet to sign anything or to send a transaction.
export interface Eip1193 {
  request(args: { method: string; params?: unknown[] }): Promise<unknown>;
  on?(event: string, fn: (...args: any[]) => void): void;
  removeListener?(event: string, fn: (...args: any[]) => void): void;
}
export interface DiscoveredWallet { id: string; name: string; icon?: string; provider: Eip1193 }
export interface Connection { walletId: string; name: string; icon?: string; address: string; chainId: number }

const CHAIN_NAMES: Record<number, string> = {
  1: "Ethereum Mainnet", 11155111: "Sepolia (testnet)", 17000: "Holesky (testnet)",
  10: "Optimism", 137: "Polygon", 42161: "Arbitrum One", 8453: "Base", 56: "BNB Chain",
};
export const chainName = (id: number) => CHAIN_NAMES[id] ?? "Chain " + id;

interface WalletCtx {
  wallets: DiscoveredWallet[];
  conn: Connection | null;
  busyId: string | null;
  error: string | null;
  connect: (w: DiscoveredWallet) => Promise<void>;
  disconnect: () => Promise<void>;
  switchToMainnet: () => Promise<void>;
  getBalance: () => Promise<string | null>;
}
const Ctx = createContext<WalletCtx | null>(null);
const KEY = "cg_wallet";

const hexToInt = (h: unknown) => parseInt(String(h), 16);
const friendly = (e: unknown): string => {
  const x = e as { code?: number; message?: string };
  if (x?.code === 4001) return "You closed the request in your wallet. Nothing was connected.";
  if (x?.code === -32002) return "A request is already open in your wallet. Open the wallet window to continue.";
  return x?.message ? String(x.message).slice(0, 200) : "The wallet could not connect.";
};

export function WalletProvider({ children }: { children: ReactNode }) {
  const [wallets, setWallets] = useState<DiscoveredWallet[]>([]);
  const [conn, setConn] = useState<Connection | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Wallet discovery (EIP-6963), with a fallback for older wallets that only set window.ethereum.
  useEffect(() => {
    const found = new Map<string, DiscoveredWallet>();
    const publish = () => setWallets(Array.from(found.values()));
    const onAnnounce = (e: Event) => {
      const d = (e as CustomEvent).detail;
      if (!d || !d.info || !d.info.uuid || !d.provider || typeof d.provider.request !== "function") return;
      const icon = typeof d.info.icon === "string" && d.info.icon.startsWith("data:image/") ? d.info.icon : undefined;
      found.set(String(d.info.uuid), {
        id: String(d.info.uuid), name: String(d.info.name ?? "Wallet").slice(0, 40), icon, provider: d.provider,
      });
      publish();
    };
    window.addEventListener("eip6963:announceProvider", onAnnounce);
    window.dispatchEvent(new Event("eip6963:requestProvider"));
    const t = window.setTimeout(() => {
      const eth = (window as unknown as { ethereum?: Eip1193 & { isMetaMask?: boolean } }).ethereum;
      if (eth && found.size === 0) {
        found.set("injected", { id: "injected", name: eth.isMetaMask ? "MetaMask" : "Browser wallet", provider: eth });
        publish();
      }
    }, 700);
    return () => { window.removeEventListener("eip6963:announceProvider", onAnnounce); window.clearTimeout(t); };
  }, []);

  const provider = useMemo(() => wallets.find((w) => w.id === conn?.walletId)?.provider ?? null, [wallets, conn?.walletId]);

  const dropLocal = useCallback(() => {
    setConn(null);
    try { localStorage.removeItem(KEY); } catch { /* storage unavailable */ }
  }, []);

  // Quietly restore a previous connection. eth_accounts never opens a wallet popup.
  useEffect(() => {
    if (conn) return;
    let id: string | null = null;
    try { id = localStorage.getItem(KEY); } catch { /* storage unavailable */ }
    const w = id ? wallets.find((x) => x.id === id) : undefined;
    if (!w) return;
    let live = true;
    (async () => {
      try {
        const accs = (await w.provider.request({ method: "eth_accounts" })) as string[];
        if (!live || !accs || !accs[0]) return;
        const chainId = hexToInt(await w.provider.request({ method: "eth_chainId" }));
        if (live) setConn({ walletId: w.id, name: w.name, icon: w.icon, address: accs[0], chainId });
      } catch { /* stay disconnected */ }
    })();
    return () => { live = false; };
  }, [wallets, conn]);

  // Follow account and network changes made inside the wallet.
  useEffect(() => {
    if (!provider || !provider.on) return;
    const onAccounts = (a: string[]) => {
      if (!a || !a.length) dropLocal();
      else setConn((c) => (c ? { ...c, address: a[0] } : c));
    };
    const onChain = (c: string) => setConn((x) => (x ? { ...x, chainId: hexToInt(c) } : x));
    provider.on("accountsChanged", onAccounts);
    provider.on("chainChanged", onChain);
    return () => {
      if (provider.removeListener) { provider.removeListener("accountsChanged", onAccounts); provider.removeListener("chainChanged", onChain); }
    };
  }, [provider, dropLocal]);

  const connect = useCallback(async (w: DiscoveredWallet) => {
    setError(null);
    setBusyId(w.id);
    try {
      const accs = (await w.provider.request({ method: "eth_requestAccounts" })) as string[];
      if (!accs || !accs[0]) throw new Error("The wallet returned no account.");
      const chainId = hexToInt(await w.provider.request({ method: "eth_chainId" }));
      setConn({ walletId: w.id, name: w.name, icon: w.icon, address: accs[0], chainId });
      try { localStorage.setItem(KEY, w.id); } catch { /* storage unavailable */ }
    } catch (e) {
      setError(friendly(e));
    } finally {
      setBusyId(null);
    }
  }, []);

  const disconnect = useCallback(async () => {
    if (provider) {
      // Best effort: MetaMask supports revoking the site's permission. Others may not.
      try { await provider.request({ method: "wallet_revokePermissions", params: [{ eth_accounts: {} }] }); } catch { /* not supported */ }
    }
    setError(null);
    dropLocal();
  }, [provider, dropLocal]);

  const switchToMainnet = useCallback(async () => {
    if (!provider) return;
    try { await provider.request({ method: "wallet_switchEthereumChain", params: [{ chainId: "0x1" }] }); }
    catch (e) { setError(friendly(e)); }
  }, [provider]);

  const getBalance = useCallback(async () => {
    if (!provider || !conn) return null;
    try {
      const h = await provider.request({ method: "eth_getBalance", params: [conn.address, "latest"] });
      return (hexToInt(h) / 1e18).toFixed(4);
    } catch { return null; }
  }, [provider, conn]);

  const value = useMemo(
    () => ({ wallets, conn, busyId, error, connect, disconnect, switchToMainnet, getBalance }),
    [wallets, conn, busyId, error, connect, disconnect, switchToMainnet, getBalance]
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useWallet(): WalletCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useWallet must be used inside WalletProvider");
  return c;
}