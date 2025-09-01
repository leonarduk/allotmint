/* src/lib/api.ts ----------------------------------------------------- */

import type {
  GroupPortfolio,
  GroupSummary,
  InstrumentDetail,
  InstrumentSummary,
  OwnerSummary,
  Portfolio,
  PerformancePoint,
  ValueAtRiskPoint,
  AlphaResponse,
  TrackingErrorResponse,
  MaxDrawdownResponse,
  Transaction,
  Alert,
  PriceEntry,
  ScreenerResult,
  VirtualPortfolio,
  CustomQuery,
  SavedQuery,
  QuoteRow,
  TradingSignal,
  ComplianceResult,
  MoverRow,
  TimeseriesSummary,
  ScenarioResult,
  TradeSuggestion,
  SectorContribution,
  RegionContribution,
  UserConfig,
} from "./types";

/* ------------------------------------------------------------------ */
/* Base URL – fall back to localhost if no Vite env vars are defined. */
/* ------------------------------------------------------------------ */
export const API_BASE =
  import.meta.env.VITE_ALLOTMINT_API_BASE ??
  import.meta.env.VITE_API_URL ??
  "http://localhost:8000";

let authToken: string | null = null;
export const setAuthToken = (token: string | null) => {
  authToken = token;
};

export async function login(idToken: string): Promise<string> {
  const res = await fetch(`${API_BASE}/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id_token: idToken }),
  });
  if (!res.ok) {
    throw new Error("Login failed");
  }
  const data = (await res.json()) as { access_token: string };
  setAuthToken(data.access_token);
  return data.access_token;
}

/* ------------------------------------------------------------------ */
/* Generic fetch helper                                                */
/* ------------------------------------------------------------------ */
export async function fetchJson<T>(
  url: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (authToken) headers.set("Authorization", `Bearer ${authToken}`);
  const res = await fetch(url, { ...init, headers });
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

/** Fetch quote snapshots for a list of symbols. */
export const getQuotes = (symbols: string[]) => {
  const params = new URLSearchParams({ symbols: symbols.join(",") });
  return fetchJson<QuoteRow[]>(`${API_BASE}/api/quotes?${params.toString()}`);
};

/** Retrieve top movers across tickers for a period. */
export const getTopMovers = (
  tickers: string[],
  days: number,
  limit = 10,
) => {
  const params = new URLSearchParams({
    tickers: tickers.join(","),
    days: String(days),
  });
  if (limit) params.set("limit", String(limit));
  return fetchJson<{ gainers: MoverRow[]; losers: MoverRow[] }>(
    `${API_BASE}/movers?${params.toString()}`,
  );
};

/** Retrieve top movers for a group portfolio. */
export const getGroupMovers = (
  slug: string,
  days: number,
  limit = 10,
  minWeight = 0,
) => {
  const params = new URLSearchParams({ days: String(days) });
  if (limit) params.set("limit", String(limit));
  if (minWeight) params.set("min_weight", String(minWeight));
  return fetchJson<{ gainers: MoverRow[]; losers: MoverRow[] }>(
    `${API_BASE}/portfolio-group/${slug}/movers?${params.toString()}`,
  );
};

/** Apply a price shock scenario to all portfolios. */
export const runScenario = (ticker: string, pct: number) => {
  const params = new URLSearchParams({ ticker, pct: String(pct) });
  return fetchJson<ScenarioResult[]>(`${API_BASE}/scenario?${params.toString()}`);
};

/** Retrieve per-ticker aggregation for a group portfolio. */
export const getGroupInstruments = (slug: string) =>
  fetchJson<InstrumentSummary[]>(
    `${API_BASE}/portfolio-group/${slug}/instruments`
  );

/** Retrieve return contribution aggregated by sector for a group portfolio. */
export const getGroupSectorContributions = (slug: string) =>
  fetchJson<SectorContribution[]>(
    `${API_BASE}/portfolio-group/${slug}/sectors`
  );

/** Retrieve return contribution aggregated by region for a group portfolio. */
export const getGroupRegionContributions = (slug: string) =>
  fetchJson<RegionContribution[]>(
    `${API_BASE}/portfolio-group/${slug}/regions`
  );

/** Fetch performance metrics for an owner */
export const getPerformance = (
  owner: string,
  days = 365,
  excludeCash = false,
) => {
  const params = new URLSearchParams({ days: String(days) });
  if (excludeCash) params.set("exclude_cash", "1");
  return fetchJson<{ owner: string; history: PerformancePoint[] }>(
    `${API_BASE}/performance/${owner}?${params.toString()}`,
  ).then((res) => res.history);
};

export const getAlphaVsBenchmark = (
  owner: string,
  benchmark: string,
  days = 365,
) =>
  fetchJson<AlphaResponse>(
    `${API_BASE}/performance/${owner}/alpha?benchmark=${benchmark}&days=${days}`,
  );

export const getTrackingError = (
  owner: string,
  benchmark: string,
  days = 365,
) =>
  fetchJson<TrackingErrorResponse>(
    `${API_BASE}/performance/${owner}/tracking-error?benchmark=${benchmark}&days=${days}`,
  );

export const getMaxDrawdown = (owner: string, days = 365) =>
  fetchJson<MaxDrawdownResponse>(
    `${API_BASE}/performance/${owner}/max-drawdown?days=${days}`,
  );

export const getGroupAlphaVsBenchmark = (
  slug: string,
  benchmark: string,
  days = 365,
) =>
  fetchJson<AlphaResponse>(
    `${API_BASE}/performance-group/${slug}/alpha?benchmark=${benchmark}&days=${days}`,
  );

export const getGroupTrackingError = (
  slug: string,
  benchmark: string,
  days = 365,
) =>
  fetchJson<TrackingErrorResponse>(
    `${API_BASE}/performance-group/${slug}/tracking-error?benchmark=${benchmark}&days=${days}`,
  );

export const getGroupMaxDrawdown = (slug: string, days = 365) =>
  fetchJson<MaxDrawdownResponse>(
    `${API_BASE}/performance-group/${slug}/max-drawdown?days=${days}`,
  );

/** Run a simple fundamentals screen across a list of tickers. */
export const getScreener = (
  tickers: string[],
  criteria: {
    peg_max?: number;
    pe_max?: number;
    de_max?: number;
    lt_de_max?: number;
    interest_coverage_min?: number;
    current_ratio_min?: number;
    quick_ratio_min?: number;
    fcf_min?: number;
    eps_min?: number;
    gross_margin_min?: number;
    operating_margin_min?: number;
    net_margin_min?: number;
    ebitda_margin_min?: number;
    roa_min?: number;
    roe_min?: number;
    roi_min?: number;
    dividend_yield_min?: number;
    dividend_payout_ratio_max?: number;
    beta_max?: number;
    shares_outstanding_min?: number;
    float_shares_min?: number;
    market_cap_min?: number;
    high_52w_max?: number;
    low_52w_max?: number;
    low_52w_min?: number;
    avg_volume_min?: number;
  } = {},
  signal?: AbortSignal,
) => {
  const params = new URLSearchParams({ tickers: tickers.join(",") });
  if (criteria.peg_max != null) params.set("peg_max", String(criteria.peg_max));
  if (criteria.pe_max != null) params.set("pe_max", String(criteria.pe_max));
  if (criteria.de_max != null) params.set("de_max", String(criteria.de_max));
  if (criteria.lt_de_max != null) params.set("lt_de_max", String(criteria.lt_de_max));
  if (criteria.interest_coverage_min != null)
    params.set("interest_coverage_min", String(criteria.interest_coverage_min));
  if (criteria.current_ratio_min != null)
    params.set("current_ratio_min", String(criteria.current_ratio_min));
  if (criteria.quick_ratio_min != null)
    params.set("quick_ratio_min", String(criteria.quick_ratio_min));
  if (criteria.fcf_min != null) params.set("fcf_min", String(criteria.fcf_min));
  if (criteria.eps_min != null) params.set("eps_min", String(criteria.eps_min));
  if (criteria.gross_margin_min != null)
    params.set("gross_margin_min", String(criteria.gross_margin_min));
  if (criteria.operating_margin_min != null)
    params.set("operating_margin_min", String(criteria.operating_margin_min));
  if (criteria.net_margin_min != null)
    params.set("net_margin_min", String(criteria.net_margin_min));
  if (criteria.ebitda_margin_min != null)
    params.set("ebitda_margin_min", String(criteria.ebitda_margin_min));
  if (criteria.roa_min != null) params.set("roa_min", String(criteria.roa_min));
  if (criteria.roe_min != null) params.set("roe_min", String(criteria.roe_min));
  if (criteria.roi_min != null) params.set("roi_min", String(criteria.roi_min));
  if (criteria.dividend_yield_min != null)
    params.set("dividend_yield_min", String(criteria.dividend_yield_min));
  if (criteria.dividend_payout_ratio_max != null)
    params.set(
      "dividend_payout_ratio_max",
      String(criteria.dividend_payout_ratio_max),
    );
  if (criteria.beta_max != null) params.set("beta_max", String(criteria.beta_max));
  if (criteria.shares_outstanding_min != null)
    params.set(
      "shares_outstanding_min",
      String(criteria.shares_outstanding_min),
    );
  if (criteria.float_shares_min != null)
    params.set("float_shares_min", String(criteria.float_shares_min));
  if (criteria.market_cap_min != null)
    params.set("market_cap_min", String(criteria.market_cap_min));
  if (criteria.high_52w_max != null)
    params.set("high_52w_max", String(criteria.high_52w_max));
  if (criteria.low_52w_max != null)
    params.set("low_52w_max", String(criteria.low_52w_max));
  if (criteria.low_52w_min != null)
    params.set("low_52w_min", String(criteria.low_52w_min));
  if (criteria.avg_volume_min != null)
    params.set("avg_volume_min", String(criteria.avg_volume_min));
  return fetchJson<ScreenerResult[]>(`${API_BASE}/screener?${params.toString()}`, { signal });
};

export const searchInstruments = (
  query: string,
  sector?: string,
  region?: string,
  signal?: AbortSignal,
) => {
  const trimmed = query.trim();
  if (!/^[\w\s.-]{1,64}$/.test(trimmed)) {
    return Promise.reject(new Error("Invalid query"));
  }
  const params = new URLSearchParams({ q: trimmed });
  if (sector && /^[A-Za-z\s]{1,64}$/.test(sector)) params.set("sector", sector);
  if (region && /^[A-Za-z\s]{1,64}$/.test(region)) params.set("region", region);
  return fetchJson<{
    ticker: string;
    name: string;
    sector?: string;
    region?: string;
  }[]>(`${API_BASE}/instrument/search?${params.toString()}`, { signal });
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
export const getInstrumentDetail = (
  ticker: string,
  days = 365,
  signal?: AbortSignal,
) =>
  fetchJson<InstrumentDetail>(
    `${API_BASE}/instrument/?ticker=${encodeURIComponent(
      ticker
    )}&days=${days}&format=json`,
    { signal },
  );


export const getTimeseries = (ticker: string, exchange = "L") =>
  fetchJson<PriceEntry[]>(`${API_BASE}/timeseries/edit?ticker=${encodeURIComponent(ticker)}&exchange=${encodeURIComponent(exchange)}`);

export const saveTimeseries = (ticker: string, exchange: string, rows: PriceEntry[]) =>
  fetchJson<{ status: string; rows: number }>(`${API_BASE}/timeseries/edit?ticker=${encodeURIComponent(ticker)}&exchange=${encodeURIComponent(exchange)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(rows),
  });

export const listTimeseries = () =>
  fetchJson<TimeseriesSummary[]>(`${API_BASE}/timeseries/admin`);

export const refetchTimeseries = (ticker: string, exchange: string) =>
  fetchJson<{ status: string; rows: number }>(
    `${API_BASE}/timeseries/admin/${encodeURIComponent(ticker)}/${encodeURIComponent(exchange)}/refetch`,
    { method: "POST" },
  );

export const rebuildTimeseriesCache = (ticker: string, exchange: string) =>
  fetchJson<{ status: string; rows: number }>(
    `${API_BASE}/timeseries/admin/${encodeURIComponent(ticker)}/${encodeURIComponent(exchange)}/rebuild_cache`,
    { method: "POST" },
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
export const getAlerts = () => fetchJson<Alert[]>(`${API_BASE}/alerts/`);

/** Retrieve alert threshold for an owner. */
export const getAlertThreshold = (owner: string) =>
  fetchJson<{ threshold: number }>(`${API_BASE}/alert-thresholds/${owner}`);

/** Update alert threshold for an owner. */
export const setAlertThreshold = (owner: string, threshold: number) =>
  fetchJson<{ threshold: number }>(`${API_BASE}/alert-thresholds/${owner}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ threshold }),
  });

export interface PushSubscriptionJSON {
  endpoint?: string;
  keys: {
    p256dh: string;
    auth: string;
  };
}

/** Store a push subscription for an owner. */
export const savePushSubscription = (
  owner: string,
  sub: PushSubscriptionJSON,
) =>
  fetchJson(`${API_BASE}/alerts/push-subscription/${owner}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(sub),
  });

/** Remove the push subscription for an owner. */
export const deletePushSubscription = (owner: string) =>
  fetchJson(`${API_BASE}/alerts/push-subscription/${owner}`, {
    method: "DELETE",
  });

// Backwards compatibility aliases
export const getAlertSettings = getAlertThreshold;
export const setAlertSettings = setAlertThreshold;

/** Retrieve trading signals generated by the backend. */
export const getTradingSignals = () =>
  fetchJson<TradingSignal[]>(`${API_BASE}/trading-agent/signals`);

/** Retrieve compliance warnings for an owner */
export const getCompliance = (owner: string) =>
  fetchJson<ComplianceResult>(`${API_BASE}/compliance/${owner}`);

/** Validate a proposed trade for an owner */
export const validateTrade = (tx: Transaction) =>
  fetchJson<ComplianceResult>(`${API_BASE}/compliance/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(tx),
  });

/** Alias for compatibility with newer API naming */
export const complianceForOwner = getCompliance;

/** Virtual portfolio endpoints */
export const getVirtualPortfolios = () =>
  fetchJson<VirtualPortfolio[]>(`${API_BASE}/virtual-portfolios`);

export const getVirtualPortfolio = (id: number | string) =>
  fetchJson<VirtualPortfolio>(`${API_BASE}/virtual-portfolios/${id}`);

export const createVirtualPortfolio = (vp: VirtualPortfolio) =>
  fetchJson<VirtualPortfolio>(`${API_BASE}/virtual-portfolios`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(vp),
  });

export const updateVirtualPortfolio = (
  id: number | string,
  vp: VirtualPortfolio,
) =>
  fetchJson<VirtualPortfolio>(`${API_BASE}/virtual-portfolios/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(vp),
  });

export const deleteVirtualPortfolio = (id: number | string) =>
  fetchJson<{ status: string }>(`${API_BASE}/virtual-portfolios/${id}`, {
    method: "DELETE",
  });

/** Retrieve backend configuration. */
export const getConfig = <T = Record<string, unknown>>() =>
  fetchJson<T>(`${API_BASE}/config`);

/** Persist configuration changes. */
export const updateConfig = (cfg: Record<string, unknown>) =>
  fetchJson<Record<string, unknown>>(`${API_BASE}/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cfg),
  });

export const getUserConfig = (owner: string) =>
  fetchJson<UserConfig>(`${API_BASE}/user-config/${owner}`);

export const updateUserConfig = (owner: string, cfg: UserConfig) =>
  fetchJson<UserConfig>(`${API_BASE}/user-config/${owner}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cfg),
  });


/** Execute a custom query against the backend. */
export const runCustomQuery = (params: CustomQuery) => {
  const query = new URLSearchParams();
  if (params.start) query.set("start", params.start);
  if (params.end) query.set("end", params.end);
  if (params.owners?.length) query.set("owners", params.owners.join(","));
  if (params.tickers?.length) query.set("tickers", params.tickers.join(","));
  if (params.metrics?.length) query.set("metrics", params.metrics.join(","));
  query.set("format", "json");
  return fetchJson<Record<string, unknown>[]>(
    `${API_BASE}/custom-query/run?${query.toString()}`,
  );
};

/** Persist a query definition on the backend. */
export const saveCustomQuery = (name: string, params: CustomQuery) =>
  fetchJson<{ id: string }>(`${API_BASE}/custom-query/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, ...params }),
  });

/** List saved queries available on the backend. */
export const listSavedQueries = () =>
  fetchJson<SavedQuery[]>(`${API_BASE}/custom-query/saved`);
/** Fetch rolling Value at Risk series for an owner. */
export const getValueAtRisk = (
  owner: string,
  opts: { days?: number; confidence?: number; excludeCash?: boolean } = {},
) => {
  const params = new URLSearchParams();
  if (opts.days != null) params.set("days", String(opts.days));
  if (opts.confidence != null)
    params.set("confidence", String(opts.confidence));
  if (opts.excludeCash) params.set("exclude_cash", "1");
  const qs = params.toString();
  return fetchJson<ValueAtRiskPoint[]>(
    `${API_BASE}/var/${owner}${qs ? `?${qs}` : ""}`
  );
};

/** Trigger a backend recomputation of VaR for an owner. */
export const recomputeValueAtRisk = (
  owner: string,
  opts: { days?: number; confidence?: number } = {}
) => {
  const params = new URLSearchParams();
  if (opts.days != null) params.set("days", String(opts.days));
  if (opts.confidence != null)
    params.set("confidence", String(opts.confidence));
  const qs = params.toString();
  return fetchJson<{ owner: string; var: unknown }>(
    `${API_BASE}/var/${owner}/recompute${qs ? `?${qs}` : ""}`,
    { method: "POST" }
  );
};

/** Request trade suggestions to rebalance a portfolio. */
export const getRebalance = (
  actual: Record<string, number>,
  target: Record<string, number>,
) =>
  fetchJson<TradeSuggestion[]>(`${API_BASE}/rebalance`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ actual, target }),
  });
