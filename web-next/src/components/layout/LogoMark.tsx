import { useEffect, useRef } from "react";
import { prefersReduced } from "../../motion/useReducedMotion";

// The shield looks toward the cursor wherever it is on the page.
export default function LogoMark({ size = 30 }: { size?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || prefersReduced() || window.matchMedia("(pointer: coarse)").matches) return;
    let raf = 0, px = 0, py = 0;
    const apply = () => {
      raf = 0;
      const b = el.getBoundingClientRect();
      const dx = px - (b.left + b.width / 2), dy = py - (b.top + b.height / 2);
      const dist = Math.hypot(dx, dy) || 1, k = Math.min(1, dist / 260);
      el.style.setProperty("--lx", ((dx / dist) * k).toFixed(3));
      el.style.setProperty("--ly", ((dy / dist) * k).toFixed(3));
    };
    const move = (e: PointerEvent) => { px = e.clientX; py = e.clientY; if (!raf) raf = requestAnimationFrame(apply); };
    const leave = () => { el.style.setProperty("--lx", "0"); el.style.setProperty("--ly", "0"); };
    window.addEventListener("pointermove", move, { passive: true });
    document.documentElement.addEventListener("pointerleave", leave);
    return () => { window.removeEventListener("pointermove", move); document.documentElement.removeEventListener("pointerleave", leave); cancelAnimationFrame(raf); };
  }, []);
  return (
    <span ref={ref} className="logomark" aria-hidden="true">
      <svg width={size} height={size} viewBox="0 0 200 210">
        <defs><linearGradient id="lmg" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#8757ff" /><stop offset="1" stopColor="#42b8ff" /></linearGradient></defs>
        <path d="M100 10 180 40v65c0 45-35 75-80 95-45-20-80-50-80-95V40z" fill="url(#lmg)" />
        <circle cx="100" cy="98" r="34" fill="rgba(9,11,22,.55)" />
        <circle className="core" cx="100" cy="98" r="18" fill="#fff" />
      </svg>
    </span>
  );
}