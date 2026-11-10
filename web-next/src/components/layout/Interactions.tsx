import { useEffect } from "react";
import { prefersReduced } from "../../motion/useReducedMotion";

const FX = ".btn, .card, .tile, .steps li, .item, .abt-card, .doc-step, .rep-row";
const TILT = ".card, .tile, .steps li, .abt-card, .doc-step";

// One delegated listener: magnetic buttons, tilt + spotlight cards, ambient glow, click ripples.
export default function Interactions() {
  useEffect(() => {
    if (prefersReduced() || window.matchMedia("(pointer: coarse)").matches) return;
    const root = document.documentElement;
    let raf = 0, ev: PointerEvent | null = null, active: HTMLElement | null = null;
    const clear = (el: HTMLElement) => ["--tx", "--ty", "--rx", "--ry"].forEach((p) => el.style.removeProperty(p));

    const frame = () => {
      raf = 0;
      if (!ev) return;
      root.style.setProperty("--gx", ev.clientX + "px");
      root.style.setProperty("--gy", ev.clientY + "px");
      const target = ev.target as Element | null;
      const t = target && target.closest ? (target.closest(FX) as HTMLElement | null) : null;
      if (active && active !== t) clear(active);
      active = t;
      if (!t) return;
      const b = t.getBoundingClientRect();
      const x = ev.clientX - b.left, y = ev.clientY - b.top, nx = x / b.width - 0.5, ny = y / b.height - 0.5;
      t.style.setProperty("--mx", x + "px"); t.style.setProperty("--my", y + "px");
      if (t.matches(".btn")) { t.style.setProperty("--tx", (nx * 10).toFixed(1) + "px"); t.style.setProperty("--ty", (ny * 8).toFixed(1) + "px"); }
      else if (t.matches(TILT)) { t.style.setProperty("--rx", (-ny * 7).toFixed(2) + "deg"); t.style.setProperty("--ry", (nx * 9).toFixed(2) + "deg"); }
    };
    const move = (e: PointerEvent) => { ev = e; if (!raf) raf = requestAnimationFrame(frame); };
    const leave = () => { if (active) clear(active); active = null; };
    const click = (e: MouseEvent) => {
      const target = e.target as Element | null;
      const t = target && target.closest ? (target.closest(".btn, .links a, .tabs a") as HTMLElement | null) : null;
      if (!t || t.matches(":disabled")) return;
      const b = t.getBoundingClientRect(), s = Math.max(b.width, b.height) * 2.2;
      const x = e.detail === 0 ? b.width / 2 : e.clientX - b.left, y = e.detail === 0 ? b.height / 2 : e.clientY - b.top;
      const r = document.createElement("span");
      r.className = "ripple";
      r.style.cssText = `left:${x}px;top:${y}px;width:${s}px;height:${s}px`;
      t.appendChild(r);
      r.addEventListener("animationend", () => r.remove());
    };
    document.addEventListener("pointermove", move, { passive: true });
    document.documentElement.addEventListener("pointerleave", leave);
    document.addEventListener("click", click);
    return () => {
      document.removeEventListener("pointermove", move);
      document.documentElement.removeEventListener("pointerleave", leave);
      document.removeEventListener("click", click);
      cancelAnimationFrame(raf);
    };
  }, []);
  return null;
}