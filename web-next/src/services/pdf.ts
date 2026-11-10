import type { Report, RiskLevel } from "../types/report";
import { LEVEL_NOTE } from "../components/report/RiskBadge";

type RGB = [number, number, number];
const COLOR: Record<RiskLevel, RGB> = {
  LOW: [14, 140, 115], MODERATE: [201, 130, 0], HIGH: [214, 78, 24], CRITICAL: [200, 30, 60], INSUFFICIENT_DATA: [110, 116, 135],
};
const LABEL: Record<RiskLevel, string> = {
  LOW: "LOW - no findings in completed checks", MODERATE: "MODERATE RISK", HIGH: "HIGH RISK", CRITICAL: "CRITICAL RISK", INSUFFICIENT_DATA: "INSUFFICIENT DATA",
};

// The built-in PDF fonts only cover Latin-1, so normalise anything else.
const clean = (s: unknown): string => String(s ?? "")
  .replace(/[\u2000-\u200B\u202F]/g, " ").replace(/[\u2018\u2019]/g, "'").replace(/[\u201C\u201D]/g, '"')
  .replace(/[\u2013\u2014]/g, "-").replace(/\u2026/g, "...").replace(/[^\x20-\x7E\u00A0-\u00FF\n]/g, "?");

export async function downloadReportPdf(r: Report): Promise<void> {
  const { jsPDF } = await import("jspdf");
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const W = 210, H = 297, M = 16, CW = W - 2 * M;
  const level: RiskLevel = LEVEL_NOTE[r.risk_level] ? r.risk_level : "INSUFFICIENT_DATA";
  const col = COLOR[level];
  const ink: RGB = [28, 32, 48], dim: RGB = [105, 112, 134];
  let y = 0;

  const ensure = (h: number) => { if (y + h > H - 16) { doc.addPage(); y = M; } };
  const para = (t: unknown, o: { size?: number; bold?: boolean; mono?: boolean; color?: RGB; indent?: number; gap?: number } = {}) => {
    const size = o.size ?? 10, ind = o.indent ?? 0, c = o.color ?? ink;
    doc.setFont(o.mono ? "courier" : "helvetica", o.bold ? "bold" : "normal");
    doc.setFontSize(size); doc.setTextColor(c[0], c[1], c[2]);
    const lines = doc.splitTextToSize(clean(t), CW - ind) as string[];
    const lh = size * 0.46;
    for (const l of lines) { ensure(lh); y += lh; doc.text(l, M + ind, y); }
    y += o.gap ?? 1.5;
  };
  const heading = (t: string) => {
    ensure(16); y += 4;
    para(t, { size: 13, bold: true, gap: 1 });
    doc.setDrawColor(215, 218, 230); doc.line(M, y, W - M, y); y += 3;
  };
  const kv = (k: string, v: string) => {
    const lines = doc.splitTextToSize(clean(v), CW - 34) as string[];
    ensure(5);
    doc.setFont("helvetica", "bold"); doc.setFontSize(9); doc.setTextColor(dim[0], dim[1], dim[2]); doc.text(k, M, y + 4);
    doc.setFont("helvetica", "normal"); doc.setTextColor(ink[0], ink[1], ink[2]);
    lines.forEach((l, i) => { if (i > 0) ensure(4.6); doc.text(l, M + 34, y + 4); y += 4.6; });
    y += 0.6;
  };

  // header band
  doc.setFillColor(9, 11, 22); doc.rect(0, 0, W, 30, "F");
  doc.setTextColor(255, 255, 255); doc.setFont("helvetica", "bold"); doc.setFontSize(18); doc.text("ChainGuard", M, 14);
  doc.setFont("helvetica", "normal"); doc.setFontSize(10); doc.setTextColor(180, 188, 210);
  doc.text("Security analysis report - read-only screening", M, 21);
  y = 38;
  const label = LABEL[level];
  doc.setFont("helvetica", "bold"); doc.setFontSize(11);
  const pw = doc.getTextWidth(label) + 12;
  doc.setFillColor(col[0], col[1], col[2]); doc.roundedRect(M, y, pw, 9, 2, 2, "F");
  doc.setTextColor(255, 255, 255); doc.text(label, M + 6, y + 6.2);
  y += 14;
  para(r.summary, { size: 11, bold: true, gap: 1 });
  para(LEVEL_NOTE[level], { size: 9.5, color: dim, gap: 3 });

  heading("Subject");
  kv("Address / key", r.subject?.key ?? "n/a");
  kv("Type", r.detected_address_type ? `${r.subject?.type} (${r.detected_address_type})` : String(r.subject?.type ?? "n/a"));
  kv("Chain", r.chain_id === 1 ? "Ethereum mainnet (1)" : "Chain " + r.chain_id);
  kv("Generated", r.generated_at);
  kv("Engine version", r.engine_version);
  kv("Report ID", r.report_id);

  if (r.explanation?.validated && r.explanation.text) {
    heading("Plain-language rewrite");
    para(`Rewritten by a local model (${r.explanation.model}). The engine summary above is authoritative; this text never changes the level.`, { size: 8.5, color: dim });
    para(r.explanation.text, { size: 10 });
  }

  heading("Checks performed");
  const cov = r.coverage ?? [];
  if (cov.length === 0) para("No coverage information was reported.", { color: dim });
  cov.forEach((c) => para(`${c.check} | source: ${c.source ?? "n/a"} | ${c.status}${c.detail ? " (" + c.detail + ")" : ""}`, { size: 9.5, gap: 0.8 }));

  heading(`Findings and evidence (${(r.evidence ?? []).length})`);
  if ((r.evidence ?? []).length === 0) para("No findings in the checks that completed.", { color: dim });
  (r.evidence ?? []).forEach((e) => {
    para(`[${String(e.severity ?? "").toUpperCase()}] ${e.claim}`, { bold: true, gap: 0.5 });
    para(`Check ${e.id} | source: ${e.source?.name ?? "n/a"} | fetched ${e.source?.fetched_at ?? "n/a"} | ${e.verified ? "verified" : "unverified"} | confidence ${Math.round((e.confidence ?? 0) * 100)}%`, { size: 8, color: dim, indent: 3, gap: 0.5 });
    const json = JSON.stringify(e.data ?? {}).replace(/,/g, ", ");
    para("Data: " + (json.length > 420 ? json.slice(0, 420) + "... (truncated)" : json), { mono: true, size: 7.5, indent: 3, gap: 3 });
  });

  if ((r.consequences ?? []).length > 0) {
    heading("What it could mean");
    r.consequences.forEach((c) => para("- " + c, { size: 9.5, gap: 1 }));
  }

  heading("Experimental ML signal");
  const scoreOk = typeof r.model?.score === "number" && r.model.status !== "not_reliable" && r.model.status !== "unavailable";
  para(`Status: ${r.model?.status ?? "unavailable"}${r.model?.reason ? " - " + r.model.reason : ""}`, { size: 9.5, gap: 1 });
  para(scoreOk ? `Model score: ${r.model.score} (experimental)` : "No score is shown because the backend did not provide a valid one.", { size: 9.5, color: dim });

  heading("Limitations");
  (r.limitations ?? []).forEach((l) => para("- " + l, { size: 9.5, gap: 1 }));

  heading("Data sources");
  (r.data_sources ?? []).forEach((s) => para(`${s.name} | fetched ${s.fetched_at}`, { size: 9.5, gap: 0.8 }));

  const pages = doc.getNumberOfPages();
  for (let i = 1; i <= pages; i++) {
    doc.setPage(i);
    doc.setFont("helvetica", "normal"); doc.setFontSize(8); doc.setTextColor(dim[0], dim[1], dim[2]);
    doc.text("ChainGuard - read-only screening aid. A result is not a guarantee of safety.", M, H - 8);
    doc.text(`Page ${i} of ${pages}`, W - M, H - 8, { align: "right" });
  }
  const day = new Date().toISOString().slice(0, 10);
  doc.save(`chainguard-${r.subject?.type ?? "report"}-${(r.subject?.key ?? "").slice(0, 10)}-${day}.pdf`);
}