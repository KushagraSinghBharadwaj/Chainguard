import type { Health } from "../types/report";
import { apiBase } from "./http";

export async function getHealth(signal?: AbortSignal): Promise<Health> {
  const r = await fetch(apiBase + "/health", { signal });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}