import { useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { useHealth } from "../../hooks/useHealth";
import LogoMark from "./LogoMark";

const LINKS = [["/", "Home"], ["/scan", "Security Scan"], ["/dashboard", "Dashboard"], ["/history", "History"], ["/about", "About"], ["/docs", "Documentation"]] as const;
const LABEL = { checking: "Checking API", online: "API online", degraded: "API degraded", offline: "API offline" } as const;

export default function Nav() {
  const [open, setOpen] = useState(false);
  const { state } = useHealth();
  return (
    <header className="nav">
      <div className="wrap nav-in">
        <Link to="/" className="logo" onClick={() => setOpen(false)}>
          <LogoMark />
          ChainGuard
        </Link>
        <button className="burger" aria-label="Menu" aria-expanded={open} onClick={() => setOpen(!open)}>☰</button>
        <nav className={"links glass" + (open ? " open" : "")} aria-label="Primary">
          {LINKS.map(([to, label]) => <NavLink key={to} to={to} end={to === "/"} onClick={() => setOpen(false)}>{label}</NavLink>)}
        </nav>
        <div className="nav-r">
          <span className={"pill " + state} title="Live result of GET /health"><i />{LABEL[state]}</span>
          <Link to="/extension" className="btn ghost sm">Install Extension</Link>
        </div>
      </div>
    </header>
  );
}