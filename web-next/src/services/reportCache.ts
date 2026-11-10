import type { Report } from "../types/report";

const KEY = "cgx_reports", MAX = 40;
type Store = { order: string[]; items: Record<string, Report> };
const read = (): Store => { try { return JSON.parse(localStorage.getItem(KEY) ?? "") as Store; } catch { return { order: [], items: {} }; } };

export function saveReport(r: Report): void {
  const s = read();
  if (!s.items[r.report_id]) s.order.push(r.report_id);
  s.items[r.report_id] = r;
  while (s.order.length > MAX) delete s.items[s.order.shift()!];
  try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { /* quota */ }
}
export const getReport = (id: string): Report | null => read().items[id] ?? null;
export function allReports(): Report[] { const s = read(); return s.order.map((id) => s.items[id]).filter(Boolean).reverse(); }
