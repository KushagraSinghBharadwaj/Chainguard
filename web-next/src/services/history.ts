import type { HistoryItem } from "../types/report";
import { api } from "./http";

export const listHistory = (limit = 100) => api<{ items: HistoryItem[] }>("/v1/history?limit=" + limit).then((r) => r.items);