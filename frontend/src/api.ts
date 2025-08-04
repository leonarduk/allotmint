/* src/lib/api.ts ----------------------------------------------------- */

import type {
  GroupPortfolio,
  GroupSummary,
  InstrumentSummary,
  OwnerSummary,
  Portfolio,
} from "./types";

/* ------------------------------------------------------------------ */
/* Base URL – fall back to localhost if no Vite env vars are defined. */
/* ------------------------------------------------------------------ */
const API_BASE =
  import.meta.env.VITE_ALLOTMINT_API_BASE ??
  import.meta.env.VITE_API_URL ??
  "http://localhost:8000";

/* ------------------------------------------------------------------ */
/* Generic fetch helper                                                */
/* ------------------------------------------------------------------ */
async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} – ${res.statusText} (${url})`);
  }
  return res.json() as Promise<T>;
}

/* ------------------------------------------------------------------ */
/* API wrappers                                                        */
/* ------------------------------------------------------------------ */
export const getOwners = () =>
  fetchJson<OwnerSummary[]>(`${API_BASE}/owners`);

export const getPortfolio = (owner: string) =>
  fetchJson<Portfolio>(`${API_BASE}/portfolio/${owner}`);

export const getGroups = () =>
  fetchJson<GroupSummary[]>(`${API_BASE}/groups`);

export const getGroupPortfolio = (slug: string) =>
  fetchJson<GroupPortfolio>(`${API_BASE}/portfolio-group/${slug}`);

export const refreshPrices = () =>
  fetchJson<{ status: string; tickers: number; timestamp?: string | null }>(
    `${API_BASE}/prices/refresh`,
    { method: "POST" }
  );

export const getGroupInstruments = (slug: string) =>
  fetchJson<InstrumentSummary[]>(
    `${API_BASE}/portfolio-group/${slug}/instruments`
  );

/**
 * Fetch price/position detail for a single instrument.
 *
 * @param ticker e.g. "VWRL.L"
 * @param days   rolling window (default 365)
 */
export const getInstrumentDetail = (ticker: string, days = 365) =>
  fetchJson<{ prices: unknown; positions: unknown }>(
    `${API_BASE}/instrument/?ticker=${encodeURIComponent(
      ticker
    )}&days=${days}&format=json`
  );
