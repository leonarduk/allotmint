import type {InstrumentSummary, OwnerSummary, Portfolio} from "./types";

const API_BASE = import.meta.env.VITE_ALLOTMINT_API_BASE || "http://localhost:8000";

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} fetching ${url}`);
  }
  return res.json() as Promise<T>;
}

export async function getOwners(): Promise<OwnerSummary[]> {
  return fetchJson<OwnerSummary[]>(`${API_BASE}/owners`);
}

export async function getPortfolio(owner: string): Promise<Portfolio> {
  return fetchJson<Portfolio>(`${API_BASE}/portfolio/${owner}`);
}

import type { GroupSummary, GroupPortfolio } from "./types";

export async function getGroups(): Promise<GroupSummary[]> {
  return fetchJson<GroupSummary[]>(`${API_BASE}/groups`);
}

export async function getGroupPortfolio(group: string): Promise<GroupPortfolio> {
  return fetchJson<GroupPortfolio>(`${API_BASE}/portfolio-group/${group}`);
}

export async function refreshPrices(): Promise<{ status: string; tickers: number; timestamp?: string | null }> {
  const res = await fetch(`${API_BASE}/prices/refresh`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} refreshing prices`);
  }
  return res.json();
}

export async function getGroupInstruments(slug: string): Promise<InstrumentSummary[]> {
  const base = import.meta.env.VITE_API_URL ?? "";
  const res  = await fetch(`${base}/portfolio-group/${slug}/instruments`);
  if (!res.ok) throw new Error(res.statusText);
  return res.json();
}
