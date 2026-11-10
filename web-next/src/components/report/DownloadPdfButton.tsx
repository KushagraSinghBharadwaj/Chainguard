import { useState } from "react";
import type { Report } from "../../types/report";

export default function DownloadPdfButton({ report, small = false, label = "Download PDF report" }: { report: Report; small?: boolean; label?: string }) {
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle");
  const click = async () => {
    setState("busy");
    try {
      const { downloadReportPdf } = await import("../../services/pdf");
      await downloadReportPdf(report);
      setState("done");
      window.setTimeout(() => setState("idle"), 2500);
    } catch { setState("error"); }
  };
  const text = state === "busy" ? "Preparing PDF…" : state === "done" ? "Downloaded ✓" : state === "error" ? "Failed, try again" : label;
  return (
    <button type="button" className={"btn ghost" + (small ? " sm" : "")} onClick={click} disabled={state === "busy"}>
      <span aria-hidden="true">⬇</span> {text}
    </button>
  );
}