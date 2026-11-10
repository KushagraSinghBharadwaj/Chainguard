import { useEffect, useState } from "react";
import { getHealth } from "../services/health";
import type { Health } from "../types/report";

export type ApiState = "checking" | "online" | "degraded" | "offline";

export function useHealth() {
  const [state, setState] = useState<ApiState>("checking");
  const [data, setData] = useState<Health | null>(null);
  useEffect(() => {
    const ctl = new AbortController();
    const run = () => {
      if (document.hidden) return;
      getHealth(ctl.signal)
        .then((h) => { setData(h); setState(h.status === "ok" && h.database === "ok" ? "online" : "degraded"); })
        .catch(() => { if (!ctl.signal.aborted) setState("offline"); });
    };
    run();
    const t = setInterval(run, 60000);
    return () => { ctl.abort(); clearInterval(t); };
  }, []);
  return { state, data };
}