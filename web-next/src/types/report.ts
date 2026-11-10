export type RiskLevel = "LOW" | "MODERATE" | "HIGH" | "CRITICAL" | "INSUFFICIENT_DATA";

export interface Evidence {
  id: string; kind: string; claim: string; severity: string; confidence: number;
  verified: boolean; data: Record<string, unknown>;
  source: { name: string; fetched_at: string };
}
export interface CoverageItem { check: string; status: string; source: string | null; detail: string | null }
export interface ModelStatus { status: string; version: string | null; pr_auc_margin?: number; reason?: string; score?: number }
export interface Explanation { text: string; model: string; source: string; validated: boolean }

export interface Report {
  report_id: string; chain_id: number;
  subject: { type: string; key: string };
  risk_level: RiskLevel; summary: string;
  evidence: Evidence[]; coverage: CoverageItem[];
  consequences: string[]; limitations: string[];
  model: ModelStatus;
  data_sources: { name: string; fetched_at: string }[];
  generated_at: string; engine_version: string;
  explanation?: Explanation;
  detected_address_type?: "eoa" | "contract";
}
export interface HistoryItem {
  report_id: string; chain_id: number; subject_type: string; subject_key: string;
  risk_level: RiskLevel; engine_version: string; summary: string; created_at: string;
}
export interface Health { status: string; service: string; version: string; timestamp: string; database: string }