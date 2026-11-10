import { useEffect, useState } from "react";

const Q = "(prefers-reduced-motion: reduce)";
export const prefersReduced = () => typeof window !== "undefined" && window.matchMedia(Q).matches;

export function useReducedMotion(): boolean {
  const [v, setV] = useState(prefersReduced());
  useEffect(() => {
    const m = window.matchMedia(Q);
    const on = () => setV(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, []);
  return v;
}