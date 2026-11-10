import type { RiskLevel } from "../../types/report";

const TEXT: Record<RiskLevel, string> = {
  LOW: "Low risk in completed checks", MODERATE: "Moderate risk", HIGH: "High risk",
  CRITICAL: "Critical risk", INSUFFICIENT_DATA: "Insufficient data",
};
export const LEVEL_NOTE: Record<RiskLevel, string> = {
  LOW: "No findings in the checks that completed. This is not a guarantee of safety.",
  MODERATE: "One or more findings need attention. Read the evidence below.",
  HIGH: "A high-risk finding is something to investigate, not a verdict that this is a scam.",
  CRITICAL: "A critical finding was reported. Review the evidence and its source before you interact.",
  INSUFFICIENT_DATA: "There was not enough data to classify this. That is not the same as low risk.",
};

export default function RiskBadge({ level }: { level: RiskLevel }) {
  const l = (TEXT[level] ? level : "INSUFFICIENT_DATA") as RiskLevel;
  return <div className={"badge lv-" + l.toLowerCase().replace("_", "-")}><i />{TEXT[l]}</div>;
}