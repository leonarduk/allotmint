import type { OwnerSummary, Portfolio } from "./types";

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
