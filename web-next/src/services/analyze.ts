import type { Report } from "../types/report";
import { postJson } from "./http";
import { saveReport } from "./reportCache";

export const ETH_ADDRESS = /^0x[0-9a-fA-F]{40}$/;

export async function analyzeAddress(address: string, signal?: AbortSignal): Promise<Report> {
  const r = await postJson<Report>("/v1/analyze", { chain_id: 1, address }, signal);
  saveReport(r);
  return r;
}