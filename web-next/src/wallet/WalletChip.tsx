import { chainName, useWallet } from "./WalletContext";
import "../pages/wallet.css";

// Small pill shown on every page: opens the wallet page, and shows the connected address.
export default function WalletChip() {
  const { conn } = useWallet();
  const short = conn ? conn.address.slice(0, 6) + "\u2026" + conn.address.slice(-4) : "";
  return (
    <a href="/wallet" className={"wal-chip" + (conn ? " on" : "")} aria-label={conn ? "Connected wallet " + short : "Connect wallet"}>
      {conn ? (
        <>
          {conn.icon ? <img src={conn.icon} alt="" width={18} height={18} /> : <span className="wal-dot" />}
          <span className="wal-short">{short}</span>
          <span className="wal-net">{chainName(conn.chainId)}</span>
        </>
      ) : (
        <><span className="wal-dot off" /><span>Connect wallet</span></>
      )}
    </a>
  );
}