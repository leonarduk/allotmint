/* src/lib/api.ts ----------------------------------------------------- */

import type {
  GroupPortfolio,
  GroupSummary,
  InstrumentSummary,
  OwnerSummary,
  Portfolio,
  PerformancePoint,
  Transaction,
  Alert,
  ScreenerResult,
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

/** List all owners and their available accounts. */
export const getOwners = () =>
  fetchJson<OwnerSummary[]>(`${API_BASE}/owners`);

/** Fetch the portfolio tree for a single owner. */
export const getPortfolio = (owner: string) =>
  fetchJson<Portfolio>(`${API_BASE}/portfolio/${owner}`);

/** List the configured groups (e.g. "adults", "children"). */
export const getGroups = () =>
  fetchJson<GroupSummary[]>(`${API_BASE}/groups`);

/** Get the aggregated portfolio for a group of owners. */
export const getGroupPortfolio = (slug: string) =>
  fetchJson<GroupPortfolio>(`${API_BASE}/portfolio-group/${slug}`);

/** Trigger a price refresh in the backend and return snapshot metadata. */
export const refreshPrices = () =>
  fetchJson<{ status: string; tickers: number; timestamp?: string | null }>(
    `${API_BASE}/prices/refresh`,
    { method: "POST" }
  );

/** Retrieve per-ticker aggregation for a group portfolio. */
export const getGroupInstruments = (slug: string) =>
  fetchJson<InstrumentSummary[]>(
    `${API_BASE}/portfolio-group/${slug}/instruments`
  );

/** Fetch performance metrics for an owner */
export const getPerformance = (owner: string, days = 365) =>
  fetchJson<PerformancePoint[]>(`${API_BASE}/performance/${owner}?days=${days}`);

/**
 * Run a simple fundamentals screen across a list of tickers.
 *
 * Additional valuation criteria may be supplied to narrow results.
 */
export const getScreener = (params: {
  tickers: string[];
  peg_max?: number;
  pe_max?: number;
  de_max?: number;
  fcf_min?: number;
}) => {
  const qs = new URLSearchParams();
  qs.set("tickers", params.tickers.join(","));
  if (params.peg_max != null) qs.set("peg_max", String(params.peg_max));
  if (params.pe_max != null) qs.set("pe_max", String(params.pe_max));
  if (params.de_max != null) qs.set("de_max", String(params.de_max));
  if (params.fcf_min != null) qs.set("fcf_min", String(params.fcf_min));
  return fetchJson<ScreenerResult[]>(`${API_BASE}/screener?${qs.toString()}`);
};

/**
 * Fetch price/position detail for a single instrument.
 *
 * The backend returns a list of daily prices and the positions where the
 * instrument is held across portfolios. This is used by the instrument detail
 * view to show recent performance alongside who owns the asset.
 *
 * @param ticker e.g. "VWRL.L"
 * @param days   rolling window (default 365)
 */
export const getInstrumentDetail = (ticker: string, days = 365) =>
  fetchJson<{ prices: unknown; positions: unknown; currency?: string | null }>(
    `${API_BASE}/instrument/?ticker=${encodeURIComponent(
      ticker
    )}&days=${days}&format=json`
  );

export const getTransactions = (params: {
  owner?: string;
  account?: string;
  start?: string;
  end?: string;
}) => {
  const query = new URLSearchParams();
  if (params.owner) query.set("owner", params.owner);
  if (params.account) query.set("account", params.account);
  if (params.start) query.set("start", params.start);
  if (params.end) query.set("end", params.end);
  const qs = query.toString();
  return fetchJson<Transaction[]>(`${API_BASE}/transactions${qs ? `?${qs}` : ""}`);
};

/** Retrieve recent alert messages from backend. */
export const getAlerts = () => fetchJson<Alert[]>(`${API_BASE}/alerts`);
/** Retrieve compliance warnings for an owner */
export const getCompliance = (owner: string) =>
  fetchJson<{ owner: string; warnings: string[] }>(
    `${API_BASE}/compliance/${owner}`
  );
