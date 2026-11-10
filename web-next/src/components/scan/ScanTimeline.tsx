import type { Step } from "../../hooks/useScan";

const ICON: Record<string, string> = { completed: "✓", partial: "~", skipped: "–", failed: "✕", error: "✕", running: "●", pending: "○" };

export default function ScanTimeline({ steps, live, elapsed, log }: { steps: Step[]; live: boolean; elapsed: number; log: string[] }) {
  return (
    <div className="glass tl-box" aria-live="polite">
      <div className="tl-head">
        <b>Analysis timeline</b>
        <span className={"src " + (live ? "live" : "")}>{live ? "● live backend events" : "from the report's coverage list"}</span>
        <span className="muted">{(elapsed / 1000).toFixed(1)}s</span>
      </div>
      <ol className="tl">
        {steps.map((s, i) => (
          <li key={s.id} className={"st-" + s.status} style={{ ["--i" as string]: i }}>
            <span className="ico">{ICON[s.status] ?? "·"}</span>
            <span>{s.label}{s.note ? <em> ({s.note})</em> : null}</span>
            <span className="muted">{s.ms != null ? s.ms + " ms" : s.status}</span>
          </li>
        ))}
      </ol>
      <details className="logbox"><summary>Raw log</summary><pre>{log.join("\n")}</pre></details>
    </div>
  );
}