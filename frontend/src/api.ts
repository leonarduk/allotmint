/* src/lib/api.ts ----------------------------------------------------- */

import type {
  GroupPortfolio,
  GroupSummary,
  InstrumentDetail,
  InstrumentDetailMini,
  InstrumentSummary,
  OwnerSummary,
  Portfolio,
  PerformancePoint,
  PerformanceResponse,
  ValueAtRiskResponse,
  VarBreakdown,
  VarScenario,
  VarBreakdownResponse,
  AlphaResponse,
  TrackingErrorResponse,
  MaxDrawdownResponse,
  ReturnComparisonResponse,
  Transaction,
  TransactionWithCompliance,
  Alert,
  PriceEntry,
  ScreenerResult,
  VirtualPortfolio,
  CustomQuery,
  SavedQuery,
  QuoteRow,
  TradingSignal,
  TradingAgentSettings,
  TradingPageData,
  OpportunityEntry,
  ComplianceResult,
  MoverRow,
  TimeseriesSummary,
  ScenarioResult,
  ScenarioEvent,
  TradeSuggestion,
  QuestResponse,
  TrailResponse,
  SectorContribution,
  RegionContribution,
  UserConfig,
  InstrumentMetadata,
  InstrumentGroupDefinition,
  ApprovalsResponse,
  NewsItem,
  Nudge,
  HoldingValue,
  MarketOverview,
  AnalyticsEventPayload,
  AnalyticsFunnelSummary,
  AnalyticsSource,
  DataQualityTimeseriesResponse,
  DataExplorerDirectory,
  DataExplorerFile,
} from "./types";
import {
  configContractSchema,
  groupPortfolioContractSchema,
  groupsContractSchema,
  ownersContractSchema,
  portfolioContractSchema,
  transactionsContractSchema,
  dataQualityTimeseriesContractSchema,
  dataQualityIssuesContractSchema,
  dataQualityAuditContractSchema,
} from "./contracts/apiContracts";

const cleanOptionalString = (value: unknown): string | null => {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
};

const validateApiBase = (url: string): string => {
  const trimmed = url.trim();
  if (!trimmed) {
    throw new Error("API base URL cannot be empty");
  }
  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    throw new Error(`Invalid API base URL: ${trimmed}`);
  }
  if (!/^https?:$/.test(parsed.protocol)) {
    throw new Error(`API base URL must use http or https protocol, got: ${parsed.protocol}`);
  }
  const cleaned = trimmed.replace(/\/+$/, "");
  return cleaned;
};

/* ------------------------------------------------------------------ */
/* Base URL – can be overridden at runtime via /config.json.          */
/* ------------------------------------------------------------------ */
export const DEFAULT_API_BASE =
  import.meta.env.VITE_ALLOTMINT_API_BASE ??
  import.meta.env.VITE_API_URL ??
  "http://localhost:8000";

// Validate at startup so a misconfigured URL surfaces immediately (CWE-918 fix).
// The inner IIFE keeps the try/catch scoped while still producing an exported binding.
// `let` (not `const`) because setApiBase() may reassign it at runtime.
export let API_BASE: string = (() => {
  try {
    return validateApiBase(DEFAULT_API_BASE);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`Failed to initialize API base URL: ${msg}`, { cause: err });
  }
})();

// Surface which backend this instance is talking to, so it's obvious in the
// browser console when running multiple local frontend/backend pairs (#5760).
if (import.meta.env.DEV) {
  console.info(`[allotmint] Connecting to backend at ${API_BASE}`);
}

export const getApiBase = () => API_BASE;

export const setApiBase = (value: string | null | undefined) => {
  if (!value) return;
  try {
    API_BASE = validateApiBase(value);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`Failed to set API base URL: ${msg}`, { cause: err });
  }
};

export type StorageLike = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
};

const TRANSIENT_HTTP_STATUSES = new Set([502, 503, 504]);
const DEFAULT_TRANSIENT_RETRY_DELAYS_MS = [250, 750];

// Bounds how long any authenticated request is allowed to hang with no
// response before it is aborted and surfaced as an error. Without this, a
// backend that accepts a connection but never replies (no status, no
// failure) leaves callers awaiting a promise that never settles, so
// page-level hooks like useFetch/useFetchWithRetry stay in `loading` forever
// with no error/timeout ever shown to the user (issue #7074). This mirrors
// the bounded-retry + explicit-error-state pattern already used for the
// /config bootstrap fetch in main.tsx (see MAX_CONFIG_FETCH_ATTEMPTS, #5073).
export const DEFAULT_FETCH_TIMEOUT_MS = 30000;

const wait = (delayMs: number) =>
  new Promise<void>((resolve) => globalThis.setTimeout(resolve, delayMs));

const isSafeRequest = (init: RequestInit) =>
  !init.method || ["GET", "HEAD", "OPTIONS"].includes(init.method.toUpperCase());

// Combines an optional caller-supplied AbortSignal (e.g. "cancel on unmount")
// with an internal timeout so a request is aborted if either fires. Returns
// the merged signal plus a `cleanup` to call once the request settles (to
// clear the timer and detach listeners) and a `timedOut` flag that is only
// true when *our* timeout fired, so callers can tell a deliberate
// caller-initiated cancellation apart from a stalled-request timeout.
function withTimeoutSignal(externalSignal: AbortSignal | undefined, timeoutMs: number) {
  const controller = new AbortController();
  const timedOut = { current: false };

  if (externalSignal?.aborted) {
    controller.abort(externalSignal.reason);
  }

  const timeoutId = globalThis.setTimeout(() => {
    timedOut.current = true;
    controller.abort();
  }, timeoutMs);

  const onExternalAbort = () => controller.abort(externalSignal?.reason);
  externalSignal?.addEventListener("abort", onExternalAbort);

  const cleanup = () => {
    globalThis.clearTimeout(timeoutId);
    externalSignal?.removeEventListener("abort", onExternalAbort);
  };

  return { signal: controller.signal, cleanup, timedOut };
}

// Retries only on transient HTTP status codes (502/503/504), not on thrown/rejected
// fetch calls — a network-level exception (offline, CORS, DNS) isn't fixed by
// retrying, and swallowing it here would hide real errors from callers.
async function fetchWithTransientRetry(
  fetchImpl: typeof fetch,
  url: string,
  init: RequestInit,
  retryDelaysMs: readonly number[],
): Promise<Response> {
  let response = await fetchImpl(url, init);
  for (
    let attempt = 0;
    attempt < retryDelaysMs.length && TRANSIENT_HTTP_STATUSES.has(response.status);
    attempt += 1
  ) {
    await wait(retryDelaysMs[attempt]);
    response = await fetchImpl(url, init);
  }
  return response;
}

const defaultGetCsrfToken = () =>
  typeof document === "undefined"
    ? null
    : document.cookie
        .split("; ")
        .find((row) => row.startsWith("csrftoken="))
        ?.split("=")[1] || null;

/**
 * Dispatched on `window` whenever an API call receives HTTP 401. A stored
 * auth token (Cognito ID token or backend JWT) can go stale independently of
 * the app's in-memory auth state — e.g. localStorage persists it past the
 * ~1h Cognito ID token lifetime, or past a Cognito session that sessionStorage
 * already dropped on tab close. Listening for this event lets the app clear
 * the stale credential and re-show the login screen instead of retrying the
 * same rejected token forever.
 */
export const UNAUTHORIZED_EVENT = "allotmint:unauthorized";

export function createClient(
  base: string | (() => string),
  token: string | null = null,
  fetchImpl: typeof fetch = fetch,
  opts: {
    getCsrfToken?: () => string | null;
    storage?: StorageLike;
    transientRetryDelaysMs?: readonly number[];
    fetchTimeoutMs?: number;
  } = {},
) {
  const resolveBase = () => (typeof base === "function" ? base() : base);
  let authToken = token;
  const getCsrfToken = opts.getCsrfToken ?? defaultGetCsrfToken;
  const storage = opts.storage;
  const transientRetryDelaysMs =
    opts.transientRetryDelaysMs ?? DEFAULT_TRANSIENT_RETRY_DELAYS_MS;
  const fetchTimeoutMs = opts.fetchTimeoutMs ?? DEFAULT_FETCH_TIMEOUT_MS;
  const TOKEN_STORAGE_KEY = "authToken";

  const setAuthToken = (t: string | null) => {
    authToken = t;
    if (!storage) return;
    if (t) storage.setItem(TOKEN_STORAGE_KEY, t);
    else storage.removeItem(TOKEN_STORAGE_KEY);
  };

  const getStoredAuthToken = () => storage?.getItem(TOKEN_STORAGE_KEY) ?? null;

  async function login(idToken: string): Promise<string> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const csrf = getCsrfToken();
    if (csrf) headers["X-CSRFToken"] = csrf;
    const res = await fetchImpl(`${resolveBase()}/token`, {
      method: "POST",
      headers,
      credentials: "include",
      body: JSON.stringify({ id_token: idToken }),
    });
    if (!res.ok) {
      throw new Error("Login failed");
    }
    const data = (await res.json()) as { access_token: string };
    setAuthToken(data.access_token);
    return data.access_token;
  }

  function logout() {
    setAuthToken(null);
    (globalThis as any).google?.accounts?.id?.disableAutoSelect?.();
  }

  // Builds and sends an authenticated request: resolves relative paths against
  // the configured base, applies the CWE-918 client-side-request-forgery
  // guards (origin + path-prefix checks), attaches the Cognito bearer token
  // and CSRF header, and on a non-2xx response dispatches UNAUTHORIZED_EVENT
  // for 401s and throws an Error carrying the backend's `detail` message when
  // available. Returns the raw `Response` on success so callers can parse the
  // body however is appropriate (JSON via fetchJson, plain text via
  // fetchText, etc.) without duplicating this security-sensitive logic.
  async function sendAuthenticated(
    url: string,
    init: RequestInit = {},
  ): Promise<Response> {
    // Support relative paths by resolving against the provided base URL.
    const resolvedBase = resolveBase();
    // Validate the base eagerly so a mis-configured API_BASE surfaces as a clear error
    // rather than a confusing TypeError deep in the guard below (CodeQL CWE-918 fix).
    let baseOrigin: string;
    try {
      baseOrigin = new URL(resolvedBase).origin;
    } catch {
      throw new Error(`API base is not a valid absolute URL: ${resolvedBase}`);
    }
    let fullUrl = url;
    try {
      // Throws for relative paths in Node/undici; succeeds for absolute URLs.
      new URL(url);
    } catch {
      fullUrl = url.startsWith("/") ? `${resolvedBase}${url}` : `${resolvedBase}/${url}`;
    }
    // Guard against client-side request forgery (CodeQL js/client-side-request-forgery, CWE-918).
    // Layer 1: origin check.
    const parsedFull = new URL(fullUrl);
    if (parsedFull.origin !== baseOrigin) {
      throw new Error(`Blocked request to unexpected host: ${parsedFull.origin}`);
    }
    // Layer 2: path-prefix check — blocks same-origin open-redirect abuse.
    // Compare pathnames so query strings and fragments at the base URL are not falsely rejected.
    const allowedPrefix = resolvedBase.replace(/\/+$/, "");
    const allowedPathPrefix = new URL(allowedPrefix).pathname.replace(/\/+$/, "");
    const requestPath = parsedFull.pathname;
    if (
      !requestPath.startsWith(`${allowedPathPrefix}/`) &&
      requestPath !== allowedPathPrefix
    ) {
      throw new Error(
        `Blocked request: ${parsedFull.href} does not start with configured API base`,
      );
    }
    // Build the request URL from the trusted base origin plus the path/query/hash
    // that just passed the checks above, rather than passing the raw `fullUrl`
    // (derived directly from the `url` argument) to fetch. This keeps the value
    // reaching fetchImpl tied to the validated `parsedFull` object so CodeQL's
    // taint tracking can see it as guarded (js/client-side-request-forgery, CWE-918).
    const safeUrl = `${baseOrigin}${parsedFull.pathname}${parsedFull.search}${parsedFull.hash}`;
    const headers = new Headers(init.headers);
    if (authToken) headers.set("Authorization", `Bearer ${authToken}`);
    const csrf = getCsrfToken();
    if (csrf) headers.set("X-CSRFToken", csrf);
    const { signal, cleanup, timedOut } = withTimeoutSignal(init.signal ?? undefined, fetchTimeoutMs);
    const requestInit = {
      ...init,
      headers,
      credentials: "include",
      signal,
    } satisfies RequestInit;
    let res: Response;
    try {
      res = isSafeRequest(init)
        ? await fetchWithTransientRetry(fetchImpl, safeUrl, requestInit, transientRetryDelaysMs)
        : await fetchImpl(safeUrl, requestInit);
    } catch (e) {
      // A stalled request (no status, no failure — see #7074) never rejects
      // fetch() on its own; our timeout is what aborts it. Surface that as a
      // clear, user-facing message rather than a bare AbortError so callers
      // (useFetch/useFetchWithRetry error states) show something actionable.
      // A caller-initiated abort (e.g. an unmounted component's own signal)
      // is left as-is — those are already swallowed by hooks' `cancelled`
      // checks and aren't a "request stalled" condition.
      if (timedOut.current) {
        const timeoutErr = new Error(
          `Request timed out after ${Math.round(fetchTimeoutMs / 1000)}s: ${safeUrl}`,
        );
        (timeoutErr as any).timeout = true;
        throw timeoutErr;
      }
      throw e;
    } finally {
      cleanup();
    }
    if (!res.ok) {
      if (res.status === 401 && typeof window !== "undefined") {
        window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
      }
      // Prefer the backend's `detail` message (e.g. actionable 401 guidance)
      // over the generic status text, so admin screens can surface it as-is
      // instead of a bare "HTTP 401 - Unauthorized" (#6058).
      let message = TRANSIENT_HTTP_STATUSES.has(res.status)
        ? "The backend service is temporarily unavailable. Please try again."
        : `HTTP ${res.status} - ${res.statusText} (${safeUrl})`;
      try {
        const body = await res.json();
        if (
          !TRANSIENT_HTTP_STATUSES.has(res.status) &&
          typeof body?.detail === "string" &&
          body.detail.trim()
        ) {
          message = body.detail;
        }
      } catch {
        // response body was not JSON; fall back to the generic message above
      }
      const err = new Error(message);
      (err as any).status = res.status;
      (err as any).headers = res.headers;
      throw err;
    }
    return res;
  }

  async function fetchJson<T>(url: string, init: RequestInit = {}): Promise<T> {
    const res = await sendAuthenticated(url, init);
    return res.json() as Promise<T>;
  }

  // Same authenticated request/error handling as fetchJson, but parses the
  // successful response body as text instead of JSON — needed for endpoints
  // like GET /logs that return PlainTextResponse rather than JSON
  // (umbrella issue #6109; authenticated-logs follow-up #6111).
  async function fetchText(url: string, init: RequestInit = {}): Promise<string> {
    const res = await sendAuthenticated(url, init);
    return res.text();
  }

  return { setAuthToken, getStoredAuthToken, login, logout, fetchJson, fetchText };
}

// Use a dynamic fetch that resolves to the current global fetch implementation
// so tests can stub/mutate globalThis.fetch after import time.
const dynamicFetch: typeof fetch = ((...args: Parameters<typeof fetch>) =>
  (globalThis.fetch as any)(...args)) as typeof fetch;

const defaultClient = createClient(() => API_BASE, null, dynamicFetch, {
  getCsrfToken: defaultGetCsrfToken,
  storage: typeof localStorage === "undefined" ? undefined : localStorage,
});

export const setAuthToken = defaultClient.setAuthToken;
export const getStoredAuthToken = defaultClient.getStoredAuthToken;
export const login = defaultClient.login;
export const logout = defaultClient.logout;
export const fetchJson = defaultClient.fetchJson;
export const fetchText = defaultClient.fetchText;

/* ------------------------------------------------------------------ */
/* API wrappers                                                        */
/* ------------------------------------------------------------------ */

// In-flight-only cache, same pattern as `getConfig`'s below (see that
// comment for the full rationale) — shares one request across concurrent
// callers, cleared as soon as it settles so a later call (e.g. after
// PlotDataContext's `refresh()` bumps `reloadToken`) still gets a fresh
// fetch rather than a stale result. Added alongside the new `/groups` fetch
// in #7189 so introducing that extra per-load request didn't raise the
// total `/owners`+`/groups`+`/config` request count for a `/plot` load
// (#7213).
type OwnersParseResult = ReturnType<typeof ownersContractSchema.parse>;
let inFlightOwnersFetch: Promise<OwnersParseResult> | null = null;

/** List all owners and their available accounts. */
export const getOwners = async () => {
  if (!inFlightOwnersFetch) {
    inFlightOwnersFetch = fetchJson<OwnerSummary[]>(`${API_BASE}/owners`)
      .then((raw) => ownersContractSchema.parse(raw))
      .finally(() => {
        inFlightOwnersFetch = null;
      });
  }
  return inFlightOwnersFetch;
};

/** Fetch the portfolio tree for a single owner. */
export const getPortfolio = async (
  owner: string,
  opts: { asOf?: string | null } = {},
) => {
  const params = new URLSearchParams();
  if (opts.asOf) params.set("as_of", opts.asOf);
  const qs = params.toString();
  return portfolioContractSchema.parse(
    await fetchJson<Portfolio>(`${API_BASE}/portfolio/${owner}${qs ? `?${qs}` : ""}`),
  );
};

/** Retrieve return contribution aggregated by sector for an owner portfolio. */
export const getOwnerSectorContributions = (
  owner: string,
  opts: { asOf?: string | null } = {},
) => {
  const params = new URLSearchParams();
  if (opts.asOf) params.set("as_of", opts.asOf);
  const qs = params.toString();
  const url = qs
    ? `${API_BASE}/portfolio/${owner}/sectors?${qs}`
    : `${API_BASE}/portfolio/${owner}/sectors`;
  return fetchJson<SectorContribution[]>(url);
};

// Same in-flight-only sharing as `getOwners` above and `getConfig` below.
type GroupsParseResult = ReturnType<typeof groupsContractSchema.parse>;
let inFlightGroupsFetch: Promise<GroupsParseResult> | null = null;

/** List the configured groups (e.g. "adults", "children"). */
export const getGroups = async () => {
  if (!inFlightGroupsFetch) {
    inFlightGroupsFetch = fetchJson<GroupSummary[]>(`${API_BASE}/groups`)
      .then((raw) => groupsContractSchema.parse(raw))
      .finally(() => {
        inFlightGroupsFetch = null;
      });
  }
  return inFlightGroupsFetch;
};

/** Get the aggregated portfolio for a group of owners. */
export const getGroupPortfolio = async (
  slug: string,
  opts: { asOf?: string | null } = {},
) => {
  const params = new URLSearchParams();
  if (opts.asOf) params.set("as_of", opts.asOf);
  const qs = params.toString();
  return groupPortfolioContractSchema.parse(
    await fetchJson<GroupPortfolio>(
      `${API_BASE}/portfolio-group/${slug}${qs ? `?${qs}` : ""}`,
    ),
  );
};

/** Trigger a price refresh in the backend and return snapshot metadata. */
export const refreshPrices = () =>
  fetchJson<{ status: string; tickers: number; timestamp?: string | null }>(
    `${API_BASE}/prices/refresh`,
    { method: "POST" }
  );

/** Fetch quote snapshots for a list of symbols. */
export const getQuotes = (symbols: string[], signal?: AbortSignal) => {
  const params = new URLSearchParams({ symbols: symbols.join(",") });
  return fetchJson<{
    name?: string | null;
    symbol: string;
    price: number | null;
    open?: number | null;
    high?: number | null;
    low?: number | null;
    previous_close?: number | null;
    volume?: number | null;
    timestamp?: number | null;
    timezone?: string | null;
    market_state?: string | null;
    currency?: string | null;
    quote_type?: string | null;
  }[]>(`${API_BASE}/api/quotes?${params.toString()}`, { signal })
    .then((rows) =>
      rows.map((r) => {
        const change =
          r.price != null && r.previous_close != null
            ? r.price - r.previous_close
            : null;
        const changePct =
          change != null && r.previous_close
            ? (change / r.previous_close) * 100
            : null;
        return {
          name: r.name ?? null,
          symbol: r.symbol,
          last: r.price ?? null,
          open: r.open ?? null,
          high: r.high ?? null,
          low: r.low ?? null,
          change,
          changePct,
          volume: r.volume ?? null,
          marketTime: r.timestamp
            ? new Date(r.timestamp * 1000).toISOString()
            : null,
          marketState: r.market_state ?? "UNKNOWN",
          currency: r.currency ?? null,
          quoteType: r.quote_type ?? null,
        } as QuoteRow;
      }),
    );
};

/** Retrieve recent news headlines for a ticker. */
export const getNews = (ticker: string, signal?: AbortSignal) => {
  const params = new URLSearchParams({ ticker });
  return fetchJson<NewsItem[]>(`${API_BASE}/news?${params.toString()}`, {
    signal,
  }).then((items) =>
    items.map((item) => ({
      headline: item.headline,
      url: item.url,
      source: cleanOptionalString(item.source ?? null),
      published_at: cleanOptionalString(item.published_at ?? null),
      stale: item.stale ?? false,
    })),
  );
};

/** Aggregate market overview data. */
export const getMarketOverview = () =>
  fetchJson<MarketOverview>(`${API_BASE}/market/overview`);

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

export type OpportunitiesResponse = {
  entries: OpportunityEntry[];
  signals: TradingSignal[];
  context: {
    source: "group" | "watchlist";
    group?: string | null;
    tickers?: string[];
    days: number;
    anomalies?: string[];
  };
};

export const getOpportunities = ({
  group,
  tickers,
  days = 1,
  limit = 10,
  minWeight = 0,
}: {
  group?: string;
  tickers?: string[];
  days?: number;
  limit?: number;
  minWeight?: number;
}) => {
  const params = new URLSearchParams({ days: String(days) });
  if (limit) params.set("limit", String(limit));
  if (minWeight) params.set("min_weight", String(minWeight));

  if (group && tickers?.length) {
    throw new Error("Specify either group or tickers, not both");
  }
  if (group) {
    params.set("group", group);
  } else if (tickers?.length) {
    params.set("tickers", tickers.join(","));
  } else {
    throw new Error("Either group or tickers must be provided");
  }

  return fetchJson<OpportunitiesResponse>(
    `${API_BASE}/opportunities?${params.toString()}`,
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

/** Retrieve available predefined events for scenario testing. */
export const getEvents = () => fetchJson<ScenarioEvent[]>(`${API_BASE}/events`);

/** Apply a predefined scenario to all portfolios. */
export const runScenario = ({
  event_id,
  horizons,
}: {
  event_id: string;
  horizons: string[];
}) => {
  const params = new URLSearchParams({
    event_id,
    horizons: horizons.join(","),
  });
  return fetchJson<ScenarioResult[]>(
    `${API_BASE}/scenario/historical?${params.toString()}`,
  );
};

export type GroupInstrumentFilters = {
  owner?: string;
  account_type?: string;
};

type GroupDataOptions = { asOf?: string | null };

const cacheKeyForGroupInstruments = (
  slug: string,
  { owner, account_type: accountType }: GroupInstrumentFilters,
  opts: GroupDataOptions = {},
) => `${slug}::${owner ?? ""}::${accountType ?? ""}::${opts.asOf ?? ""}`;

type GroupInstrumentCacheEntry = {
  promise: Promise<InstrumentSummary[]>;
  value?: InstrumentSummary[];
};

const groupInstrumentCache = new Map<string, GroupInstrumentCacheEntry>();

/** Retrieve per-ticker aggregation for a group portfolio. */
export const getGroupInstruments = (
  slug: string,
  filters: GroupInstrumentFilters = {},
  opts: GroupDataOptions = {},
) => {
  const params = new URLSearchParams();
  if (filters.owner) params.set("owner", filters.owner);
  const accountType = filters.account_type;
  if (accountType) params.set("account_type", accountType);
  if (opts.asOf) params.set("as_of", opts.asOf);
  const query = params.toString();
  const url = query
    ? `${API_BASE}/portfolio-group/${slug}/instruments?${query}`
    : `${API_BASE}/portfolio-group/${slug}/instruments`;
  return fetchJson<InstrumentSummary[]>(url);
};

export const getCachedGroupInstruments = (
  slug: string,
  filters: GroupInstrumentFilters = {},
  opts: GroupDataOptions = {},
) => {
  const key = cacheKeyForGroupInstruments(slug, filters, opts);
  const existing = groupInstrumentCache.get(key);
  if (existing?.value) {
    return Promise.resolve(existing.value);
  }

  if (existing) {
    return existing.promise.then((rows) => {
      existing.value = rows;
      return rows;
    });
  }

  const promise = getGroupInstruments(slug, filters, opts)
    .then((rows) => {
      const entry = groupInstrumentCache.get(key);
      if (entry) entry.value = rows;
      return rows;
    })
    .catch((err) => {
      // A failed request must not poison the cache: leaving the rejected
      // promise cached would make every subsequent caller (e.g. a user
      // clicking "Retry") replay the same failure forever with no new
      // network request, recoverable only by a full page reload. Evict the
      // entry so the next call issues a fresh request instead.
      const entry = groupInstrumentCache.get(key);
      if (entry && entry.promise === promise) {
        groupInstrumentCache.delete(key);
      }
      throw err;
    });

  groupInstrumentCache.set(key, { promise });
  return promise;
};

export const clearGroupInstrumentCache = (slug?: string) => {
  if (!slug) {
    groupInstrumentCache.clear();
    return;
  }
  const prefix = `${slug}::`;
  for (const key of groupInstrumentCache.keys()) {
    if (key.startsWith(prefix)) {
      groupInstrumentCache.delete(key);
    }
  }
};

/** Retrieve return contribution aggregated by sector for a group portfolio. */
export const getGroupSectorContributions = (
  slug: string,
  opts: { asOf?: string | null } = {},
) => {
  const params = new URLSearchParams();
  if (opts.asOf) params.set("as_of", opts.asOf);
  const qs = params.toString();
  const url = qs
    ? `${API_BASE}/portfolio-group/${slug}/sectors?${qs}`
    : `${API_BASE}/portfolio-group/${slug}/sectors`;
  return fetchJson<SectorContribution[]>(url);
};

/** Retrieve return contribution aggregated by region for a group portfolio. */
export const getGroupRegionContributions = (
  slug: string,
  opts: { asOf?: string | null } = {},
) => {
  const params = new URLSearchParams();
  if (opts.asOf) params.set("as_of", opts.asOf);
  const qs = params.toString();
  const url = qs
    ? `${API_BASE}/portfolio-group/${slug}/regions?${qs}`
    : `${API_BASE}/portfolio-group/${slug}/regions`;
  return fetchJson<RegionContribution[]>(url);
};

/** Fetch performance metrics for an owner */
export const getPerformance = (
  owner: string,
  days = 365,
  excludeCash = false,
  opts: { asOf?: string | null } = {},
): Promise<PerformanceResponse> => {
  const params = new URLSearchParams({ days: String(days) });
  if (excludeCash) params.set("exclude_cash", "1");
  if (opts.asOf) params.set("as_of", opts.asOf);
  const base = fetchJson<{
    owner: string;
    history: PerformancePoint[];
    reporting_date?: string | null;
    previous_date?: string | null;
    data_quality_issues?: {
      date: string;
      value: number;
      previous_value: number;
      next_value: number;
    }[];
  }>(
    `${API_BASE}/performance/${owner}?${params.toString()}`,
  );
  const twr = fetchJson<{ owner: string; time_weighted_return: number | null }>(
    `${API_BASE}/performance/${owner}/twr?days=${days}${
      opts.asOf ? `&as_of=${encodeURIComponent(opts.asOf)}` : ""
    }`,
  );
  const xirr = fetchJson<{ owner: string; xirr: number | null }>(
    `${API_BASE}/performance/${owner}/xirr?days=${days}${
      opts.asOf ? `&as_of=${encodeURIComponent(opts.asOf)}` : ""
    }`,
  );
  return Promise.all([base, twr, xirr]).then(([p, t, x]) => ({
    history: p.history,
    time_weighted_return: t.time_weighted_return,
    xirr: x.xirr,
    reportingDate: p.reporting_date ?? null,
    previousDate: p.previous_date ?? null,
    dataQualityIssues:
      p.data_quality_issues?.map((issue) => ({
        date: issue.date,
        value: issue.value,
        previousValue: issue.previous_value,
        nextValue: issue.next_value,
      })) ?? [],
  }));
};

export const getAlphaVsBenchmark = (
  owner: string,
  benchmark: string,
  days = 365,
  opts: { asOf?: string | null } = {},
) => {
  const params = new URLSearchParams({ benchmark, days: String(days) });
  if (opts.asOf) params.set("as_of", opts.asOf);
  return fetchJson<AlphaResponse>(
    `${API_BASE}/performance/${owner}/alpha?${params.toString()}`,
  );
};

export const getPortfolioHoldings = (owner: string, date: string) =>
  fetchJson<{ owner: string; date: string; holdings: HoldingValue[] }>(
    `${API_BASE}/performance/${owner}/holdings?date=${encodeURIComponent(date)}`,
  );

export const getTrackingError = (
  owner: string,
  benchmark: string,
  days = 365,
  opts: { asOf?: string | null } = {},
) => {
  const params = new URLSearchParams({ benchmark, days: String(days) });
  if (opts.asOf) params.set("as_of", opts.asOf);
  return fetchJson<TrackingErrorResponse>(
    `${API_BASE}/performance/${owner}/tracking-error?${params.toString()}`,
  );
};

export const getMaxDrawdown = (
  owner: string,
  days = 365,
  opts: { asOf?: string | null } = {},
) => {
  const params = new URLSearchParams({ days: String(days) });
  if (opts.asOf) params.set("as_of", opts.asOf);
  return fetchJson<MaxDrawdownResponse>(
    `${API_BASE}/performance/${owner}/max-drawdown?${params.toString()}`,
  );
};

export const getReturnComparison = (owner: string, days = 365) =>
  fetchJson<ReturnComparisonResponse>(
    `${API_BASE}/returns/compare?owner=${encodeURIComponent(owner)}&days=${days}`,
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

/** Fetch combined performance metrics for a group (mirrors getPerformance). */
export const getGroupPerformance = (
  slug: string,
  days = 365,
  excludeCash = false,
  opts: { asOf?: string | null } = {},
): Promise<PerformanceResponse> => {
  const params = new URLSearchParams({ days: String(days) });
  if (excludeCash) params.set("exclude_cash", "1");
  if (opts.asOf) params.set("as_of", opts.asOf);
  const base = fetchJson<{
    group: string;
    history: PerformancePoint[];
    reporting_date?: string | null;
    previous_date?: string | null;
    data_quality_issues?: {
      date: string;
      value: number;
      previous_value: number;
      next_value: number;
    }[];
  }>(
    `${API_BASE}/performance-group/${slug}?${params.toString()}`,
  );
  const twr = fetchJson<{
    group: string;
    time_weighted_return: number | null;
    partial?: boolean;
    missing_members?: string[];
  }>(
    `${API_BASE}/performance-group/${slug}/twr?days=${days}${
      opts.asOf ? `&as_of=${encodeURIComponent(opts.asOf)}` : ""
    }`,
  );
  const xirr = fetchJson<{
    group: string;
    xirr: number | null;
    partial?: boolean;
    missing_members?: string[];
  }>(
    `${API_BASE}/performance-group/${slug}/xirr?days=${days}${
      opts.asOf ? `&as_of=${encodeURIComponent(opts.asOf)}` : ""
    }`,
  );
  // #7228 (DeepSeek review round 2): a Promise.all here meant a single
  // failing metric endpoint (e.g. twr or xirr timing out) would reject the
  // whole call and blank the group performance dashboard, even though the
  // base history request succeeded. Settle the three requests independently
  // -- the base history is still required (without it there is nothing to
  // chart, so its rejection propagates), but a failed twr/xirr degrades to
  // `null` (rendered as "unavailable" by the caller) instead of taking the
  // whole response down with it.
  return Promise.allSettled([base, twr, xirr]).then(([pResult, tResult, xResult]) => {
    if (pResult.status === "rejected") {
      throw pResult.reason;
    }
    const p = pResult.value;
    const t = tResult.status === "fulfilled" ? tResult.value : null;
    const x = xResult.status === "fulfilled" ? xResult.value : null;

    // #7228: a missing member ledger means TWR/XIRR were computed from an
    // incomplete cash-flow picture -- surface that rather than presenting
    // either figure as an exact number (MUST FIX 1, review round 2).
    const missingMembers = Array.from(
      new Set([...(t?.missing_members ?? []), ...(x?.missing_members ?? [])]),
    );
    return {
      history: p.history,
      time_weighted_return: t?.time_weighted_return ?? null,
      xirr: x?.xirr ?? null,
      reportingDate: p.reporting_date ?? null,
      previousDate: p.previous_date ?? null,
      dataQualityIssues:
        p.data_quality_issues?.map((issue) => ({
          date: issue.date,
          value: issue.value,
          previousValue: issue.previous_value,
          nextValue: issue.next_value,
        })) ?? [],
      partial: Boolean(t?.partial || x?.partial),
      missingMembers,
    };
  });
};

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

/**
 * Cheap up-front probe for whether the screener is available in this
 * deployment (i.e. the paid screener package is installed), without running
 * a real screen. The backend rejects an unavailable screener with HTTP 402
 * before it even validates the ticker list (see require_core() in
 * backend/routes/screener.py), so probing with an empty ticker list is
 * enough to tell the two cases apart: a 402 means the feature is gated,
 * anything else -- including the 400 "no tickers supplied" the backend
 * returns when the feature *is* available -- means it can be used. Used to
 * gate the screener UI before the user fills in any filters (#7221).
 */
export const checkScreenerAvailable = async (
  signal?: AbortSignal,
): Promise<boolean> => {
  try {
    await getScreener([], {}, signal);
    return true;
  } catch (e) {
    return (e as { status?: number } | undefined)?.status !== 402;
  }
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

export const getInstrumentIntraday = (
  ticker: string,
  signal?: AbortSignal,
) =>
  fetchJson<{ ticker: string; prices: { timestamp: string; close: number }[] }>(
    `${API_BASE}/instrument/intraday?ticker=${encodeURIComponent(ticker)}`,
    { signal },
  );

/**
 * Retry `attempt` up to `maxAttempts` times on HTTP 429 responses using
 * exponential backoff. If the server provides a `Retry-After` header it takes
 * precedence. Shared by {@link fetchInstrumentDetailWithRetry} and
 * {@link fetchInstrumentBatchWithRetry} so the two endpoints' 429 handling
 * can't drift apart.
 */
async function retryOn429<T>(
  attempt: () => Promise<T>,
  signal?: AbortSignal,
  maxAttempts = 3,
): Promise<T> {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      return await attempt();
    } catch (e) {
      const err = e instanceof Error ? e : new Error(String(e));
      const status = (err as any).status;
      if (status !== 429 && !err.message.includes("HTTP 429")) {
        throw err;
      }
      if (i === maxAttempts - 1) {
        throw err;
      }

      // Prefer server-provided Retry-After header over exponential backoff
      let delay: number | undefined;
      const retryAfter =
        (err as any).headers?.get?.("Retry-After") ??
        (err as any).response?.headers?.get?.("Retry-After");
      if (retryAfter) {
        const seconds = Number(retryAfter);
        if (!Number.isNaN(seconds)) {
          delay = seconds * 1000;
        } else {
          const dateMs = Date.parse(retryAfter);
          if (!Number.isNaN(dateMs)) delay = dateMs - Date.now();
        }
      }
      if (delay == null || delay <= 0) {
        delay = 500 * 2 ** i;
      }
      delay += Math.random() * 100;

      await new Promise<void>((resolve, reject) => {
        const timeout = setTimeout(resolve, delay);
        signal?.addEventListener(
          "abort",
          () => {
            clearTimeout(timeout);
            reject(new DOMException("Aborted", "AbortError"));
          },
          { once: true },
        );
      });
    }
  }
  // If all retries exhausted without success
  throw new Error("HTTP 429 – Too Many Requests");
}

/**
 * Wrapper around {@link getInstrumentDetail} with basic retry logic for rate limits.
 * Retries up to `maxAttempts` times on HTTP 429 responses using exponential
 * backoff. If the server provides a `Retry-After` header it takes precedence.
 */
export function fetchInstrumentDetailWithRetry(
  ticker: string,
  days = 365,
  signal?: AbortSignal,
  maxAttempts = 3,
): Promise<InstrumentDetail> {
  return retryOn429(() => getInstrumentDetail(ticker, days, signal), signal, maxAttempts);
}

export interface InstrumentBatchEntry {
  prices: unknown;
  mini?: InstrumentDetailMini;
}

export interface InstrumentBatchResponse {
  instruments: Record<string, InstrumentBatchEntry>;
  empty: string[];
  unknown: string[];
}

/**
 * Fetch price history for many tickers in one request (GET /instrument/batch).
 *
 * Response buckets `instruments` (resolved, has prices), `empty` (resolved,
 * no rows) and `unknown` (does not resolve) partition the de-duplicated
 * `tickers` list -- see the endpoint's docstring for the full contract.
 * `mini` is omitted from every entry unless `includeMini` is set.
 */
export const getInstrumentBatch = (
  tickers: string[],
  days = 365,
  includeMini = false,
  signal?: AbortSignal,
) =>
  fetchJson<InstrumentBatchResponse>(
    `${API_BASE}/instrument/batch?tickers=${encodeURIComponent(
      tickers.join(","),
    )}&days=${days}&include_mini=${includeMini}`,
    { signal },
  );

/** {@link getInstrumentBatch} with the same 429 retry/backoff policy as {@link fetchInstrumentDetailWithRetry}. */
export function fetchInstrumentBatchWithRetry(
  tickers: string[],
  days = 365,
  includeMini = false,
  signal?: AbortSignal,
  maxAttempts = 3,
): Promise<InstrumentBatchResponse> {
  return retryOn429(
    () => getInstrumentBatch(tickers, days, includeMini, signal),
    signal,
    maxAttempts,
  );
}


export const getTimeseries = (ticker: string, exchange = "L") =>
  fetchJson<PriceEntry[]>(`${API_BASE}/timeseries/edit?ticker=${encodeURIComponent(ticker)}&exchange=${encodeURIComponent(exchange)}`);

export const saveTimeseries = (ticker: string, exchange: string, rows: PriceEntry[]) =>
  fetchJson<{ status: string; rows: number }>(`${API_BASE}/timeseries/edit?ticker=${encodeURIComponent(ticker)}&exchange=${encodeURIComponent(exchange)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(rows),
  });

export const moveTimeseries = (ticker: string, sourceExchange: string, destinationExchange: string) =>
  fetchJson<{ status: string; rows: number; ticker: string; exchange: string }>(
    `${API_BASE}/timeseries/edit/move?ticker=${encodeURIComponent(ticker)}&source_exchange=${encodeURIComponent(sourceExchange)}&destination_exchange=${encodeURIComponent(destinationExchange)}`,
    { method: "POST" },
  );

export const getInstrumentMetadata = (ticker: string, exchange: string) =>
  fetchJson<(InstrumentMetadata & Record<string, unknown>) | null>(
    `${API_BASE}/instrument/admin/${encodeURIComponent(exchange)}/${encodeURIComponent(ticker)}`,
  );

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

// Data explorer (read-only browsing of the backend data/ area)
export const listDataExplorerDirectory = (path: string = "") =>
  fetchJson<DataExplorerDirectory>(
    `${API_BASE}/data-explorer/tree?path=${encodeURIComponent(path)}`,
  );

export const getDataExplorerFile = (path: string) =>
  fetchJson<DataExplorerFile>(
    `${API_BASE}/data-explorer/file?path=${encodeURIComponent(path)}`,
  );

// Instrument metadata admin
export const listInstrumentMetadata = () =>
  fetchJson<InstrumentMetadata[]>(`${API_BASE}/instrument/admin`);

export const listInstrumentGroups = () =>
  fetchJson<string[]>(`${API_BASE}/instrument/admin/groups`);

export const listInstrumentGroupingDefinitions = () =>
  fetchJson<InstrumentGroupDefinition[]>(`${API_BASE}/instrument/admin/groupings`);

type InstrumentGroupMutationResponse = {
  status: string;
  group: string;
  groups: string[];
};

export const createInstrumentGroup = (name: string) =>
  fetchJson<InstrumentGroupMutationResponse>(`${API_BASE}/instrument/admin/groups`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });

export const assignInstrumentGroup = (ticker: string, exchange: string, group: string) =>
  fetchJson<InstrumentGroupMutationResponse>(
    `${API_BASE}/instrument/admin/${encodeURIComponent(exchange)}/${encodeURIComponent(ticker)}/group`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ group }),
    },
  );

export const clearInstrumentGroup = (ticker: string, exchange: string) =>
  fetchJson<{ status: string }>(
    `${API_BASE}/instrument/admin/${encodeURIComponent(exchange)}/${encodeURIComponent(ticker)}/group`,
    {
      method: "DELETE",
    },
  );

export const createInstrumentMetadata = (
  ticker: string,
  exchange: string,
  payload: InstrumentMetadata,
) =>
  fetchJson<InstrumentMetadata>(
    `${API_BASE}/instrument/admin/${encodeURIComponent(exchange)}/${encodeURIComponent(ticker)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );

export const updateInstrumentMetadata = (
  ticker: string,
  exchange: string,
  payload: InstrumentMetadata,
) =>
  fetchJson<InstrumentMetadata>(
    `${API_BASE}/instrument/admin/${encodeURIComponent(exchange)}/${encodeURIComponent(ticker)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );

export type InstrumentMetadataRefreshResponse = {
  status: string;
  metadata: InstrumentMetadata & Record<string, unknown>;
  changes: Record<string, { from: unknown; to: unknown }>;
};

export const refreshInstrumentMetadata = (
  ticker: string,
  exchange: string,
) =>
  fetchJson<InstrumentMetadataRefreshResponse>(
    `${API_BASE}/instrument/admin/${encodeURIComponent(exchange)}/${encodeURIComponent(ticker)}/refresh`,
    {
      method: "POST",
    },
  );

export const confirmInstrumentMetadata = (
  ticker: string,
  exchange: string,
) =>
  fetchJson<InstrumentMetadataRefreshResponse>(
    `${API_BASE}/instrument/admin/${encodeURIComponent(exchange)}/${encodeURIComponent(ticker)}/refresh`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ preview: false }),
    },
  );


export const getTransactions = async (params: {
  owner?: string;
  account?: string;
  start?: string;
  end?: string;
  type?: string;
}) => {
  const query = new URLSearchParams();
  if (params.owner) query.set("owner", params.owner);
  if (params.account) query.set("account", params.account);
  if (params.start) query.set("start", params.start);
  if (params.end) query.set("end", params.end);
  if (params.type) query.set("type", params.type);
  const qs = query.toString();
  return transactionsContractSchema.parse(
    await fetchJson<Transaction[]>(`${API_BASE}/transactions${qs ? `?${qs}` : ""}`),
  );
};

export interface CreateTransactionPayload {
  owner: string;
  account: string;
  ticker: string;
  date: string;
  price_gbp: number;
  units: number;
  reason: string;
  fees?: number;
  comments?: string;
}

export interface ManualHoldingPayload {
  owner: string;
  account: string;
  ticker: string;
  value_gbp?: number;
  units?: number;
  price_gbp?: number;
  currency?: string;
}

export interface ManualHoldingAccount {
  account_type: string;
  currency: string;
  holdings: Array<Record<string, unknown>>;
  holding_count: number;
}

export const createTransaction = (payload: CreateTransactionPayload) =>
  fetchJson<Transaction>(`${API_BASE}/transactions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

export const createManualHolding = (payload: ManualHoldingPayload) =>
  fetchJson<{
    status: string;
    owner: string;
    account: string;
    holding: Record<string, unknown>;
  }>(`${API_BASE}/holdings/manual`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

export const getManualHoldings = (owner: string) =>
  fetchJson<{ owner: string; accounts: ManualHoldingAccount[] }>(
    `${API_BASE}/holdings/manual?owner=${encodeURIComponent(owner)}`,
  );

export const updateTransaction = (id: string, payload: CreateTransactionPayload) =>
  fetchJson<Transaction>(`${API_BASE}/transactions/${encodeURIComponent(id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

export const deleteTransaction = (id: string) =>
  fetchJson<{ status: string }>(`${API_BASE}/transactions/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });

export const getDividends = (params?: {
  owner?: string;
  account?: string;
  start?: string;
  end?: string;
  ticker?: string;
}) => {
  const query = new URLSearchParams();
  if (params?.owner) query.set("owner", params.owner);
  if (params?.account) query.set("account", params.account);
  if (params?.start) query.set("start", params.start);
  if (params?.end) query.set("end", params.end);
  if (params?.ticker) query.set("ticker", params.ticker);
  const qs = query.toString();
  return fetchJson<Transaction[]>(`${API_BASE}/dividends${qs ? `?${qs}` : ""}`);
};

/** Retrieve recent alert messages from backend. */
export const getAlerts = () => fetchJson<Alert[]>(`${API_BASE}/alerts/`);

/** Retrieve reminder nudges generated by the backend. */
export const getNudges = () => fetchJson<Nudge[]>(`${API_BASE}/nudges/`);

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

/** Subscribe a user to reminder nudges or update frequency. */
export const subscribeNudges = (user: string, frequency: number) => {
  const freq = Math.min(Math.max(Math.round(frequency), 1), 30);
  return fetchJson(`${API_BASE}/nudges/subscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user, frequency: freq }),
  });
};

/** Snooze nudges for a user for ``days`` days. */
export const snoozeNudges = (user: string, days: number) =>
  fetchJson(`${API_BASE}/nudges/snooze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user, days }),
  });

// Backwards compatibility aliases
export const getAlertSettings = getAlertThreshold;
export const setAlertSettings = setAlertThreshold;

/** Retrieve trading signals generated by the backend. */
export const getTradingSignals = () =>
  fetchJson<TradingSignal[]>(`${API_BASE}/trading-agent/signals`);

/** Retrieve the signals and the active thresholds that produced them. */
export const getTradingPageData = async (): Promise<TradingPageData> => {
  const [signals, settings] = await Promise.all([
    getTradingSignals(),
    fetchJson<TradingAgentSettings>(`${API_BASE}/trading-agent/settings`),
  ]);
  return { signals, settings };
};

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

/** Fetch transactions with compliance warnings */
export const getTransactionsWithCompliance = (
  owner: string,
  opts: { ticker?: string; account?: string } = {},
) => {
  const params = new URLSearchParams({ owner });
  if (opts.ticker) params.set("ticker", opts.ticker);
  if (opts.account) params.set("account", opts.account);
  return fetchJson<{ transactions: TransactionWithCompliance[] }>(
    `${API_BASE}/transactions/compliance?${params.toString()}`,
  );
};

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

// Shared in-flight-only `/config` fetch (cleared as soon as it settles, on
// either success or failure — see the `.finally` below). This is narrower
// than `getCachedGroupInstruments`'s cache above (`groupInstrumentCache`),
// which persists the *resolved value* indefinitely; that persistence is
// exactly what #7213 needs to avoid here, since a persistent cache would
// "cache a stale config across an intentional refresh" (one of #7213's own
// stated failure modes) whenever Support.tsx re-reads `/config` right after
// `updateConfig`. Every plain `getConfig()` call — ConfigContext's bootstrap
// effect, Support.tsx's re-reads — collapses onto whichever fetch is
// already in flight instead of starting its own. This is what most of the
// "/config fetched 4x per load" in #7213 turned out to be: React StrictMode
// double-invokes each mounting component's effects in dev, so
// ConfigContext's own single effect alone produced two of those four
// requests before this cache existed.
//
// A caller that passes its own `init` (main.tsx's Root, which needs to
// abort and retry the fetch on its own timeout — see MAX_CONFIG_FETCH_ATTEMPTS,
// #5073) is deliberately routed around the cache: folding a caller-owned
// AbortSignal into a fetch other callers are also awaiting would let one
// caller's abort/timeout reject everyone else's request too.
//
// Concurrent no-signal callers all resolve to the *same* parsed object by
// reference (not a fresh clone per caller). No current caller mutates it —
// callers only read config fields — but that is an invariant a future
// caller needs to keep, not something enforced here.
type ConfigParseResult = ReturnType<typeof configContractSchema.parse>;
let inFlightConfigFetch: Promise<ConfigParseResult> | null = null;

/** Retrieve backend configuration. */
export const getConfig = async <T = Record<string, unknown>>(
  init?: RequestInit,
) => {
  if (init) {
    return configContractSchema.parse(await fetchJson<T>(`${API_BASE}/config`, init));
  }
  if (!inFlightConfigFetch) {
    inFlightConfigFetch = fetchJson<T>(`${API_BASE}/config`)
      .then((raw) => configContractSchema.parse(raw))
      .finally(() => {
        inFlightConfigFetch = null;
      });
  }
  return inFlightConfigFetch;
};

/**
 * Persist configuration changes. Does not invalidate `inFlightConfigFetch`:
 * if a plain `getConfig()` call is already in flight the instant an update
 * lands, that caller joins the pre-update response rather than seeing the
 * new value. Narrow in practice — `Support.tsx` only re-reads `/config`
 * *after* `updateConfig` resolves, by which time nothing is left in flight —
 * but a future caller racing an update against a fresh page load should be
 * aware a stale value can still be joined here.
 */
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

export const getApprovals = async (owner: string) => {
  try {
    return await fetchJson<ApprovalsResponse>(
      `${API_BASE}/accounts/${owner}/approvals`,
    );
  } catch (err) {
    console.error("failed to fetch approvals for", owner, err);
    throw err;
  }
};

export const addApproval = async (
  owner: string,
  ticker: string,
  approved_on: string,
) => {
  if (!ticker) throw new Error("ticker is required");
  if (!approved_on) throw new Error("approved_on is required");
  try {
    return await fetchJson<ApprovalsResponse>(
      `${API_BASE}/accounts/${owner}/approvals`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker, approved_on }),
      },
    );
  } catch (err) {
    console.error("failed to add approval for", owner, ticker, err);
    throw err;
  }
};

export const removeApproval = async (owner: string, ticker: string) => {
  try {
    return await fetchJson<ApprovalsResponse>(
      `${API_BASE}/accounts/${owner}/approvals`,
      {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker }),
      },
    );
  } catch (err) {
    console.error("failed to remove approval for", owner, ticker, err);
    throw err;
  }
};

export const requestApproval = async (owner: string, ticker: string) => {
  if (!ticker) throw new Error("ticker is required");
  try {
    return await fetchJson<{ requests: { ticker: string; requested_on: string }[] }>(
      `${API_BASE}/accounts/${owner}/approval-requests`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker }),
      },
    );
  } catch (err) {
    console.error("failed to request approval for", owner, ticker, err);
    throw err;
  }
};


/** Execute a custom query against the backend. */
export const runCustomQuery = async (params: CustomQuery) => {
  const { results } = await fetchJson<{ results: Record<string, unknown>[] }>(
    `${API_BASE}/custom-query/run`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...params, format: "json" }),
    },
  );
  return results;
};

/** Persist a query definition on the backend. */
export const saveCustomQuery = (name: string, params: CustomQuery) =>
  fetchJson<{ id: string }>(`${API_BASE}/custom-query/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, ...params }),
  });

/** List saved queries available on the backend. */
export function listSavedQueries(opts?: { detailed?: true }): Promise<SavedQuery[]>;
export function listSavedQueries(opts: { detailed: false }): Promise<string[]>;
export function listSavedQueries(opts: { detailed?: boolean } = {}) {
  const detailed = opts.detailed ?? true;
  if (detailed) {
    return fetchJson<SavedQuery[]>(`${API_BASE}/custom-query/saved?detailed=1`);
  }
  return fetchJson<string[]>(`${API_BASE}/custom-query/saved`);
}
/** Fetch Value at Risk metrics for an owner. */
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
  return fetchJson<ValueAtRiskResponse>(
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
  return fetchJson<{ owner: string; var: Record<string, number | null> }>(
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

/** Fetch per-ticker VaR contribution breakdown for an owner. */
export const getVarBreakdown = (
  owner: string,
  opts: { days?: number; confidence?: number; horizonDays?: number } = {},
): Promise<VarBreakdownResponse> => {
  const params = new URLSearchParams();
  if (opts.days != null) params.set("days", String(opts.days));
  if (opts.confidence != null)
    params.set("confidence", String(opts.confidence));
  if (opts.horizonDays != null)
    params.set("horizon_days", String(opts.horizonDays));
  const qs = params.toString();
  return fetchJson<{
    breakdown?: VarBreakdown[];
    scenarios?: VarScenario[];
    var_date?: string | null;
    var_loss_percent?: number | null;
  } | VarBreakdown[]>(
    `${API_BASE}/var/${owner}/breakdown${qs ? `?${qs}` : ""}`
  ).then((response) => (
    Array.isArray(response)
      ? { breakdown: response, scenarios: [], varDate: null, varLossPercent: null }
      : {
          breakdown: response.breakdown ?? [],
          scenarios: response.scenarios ?? [],
          varDate: response.var_date ?? null,
          varLossPercent: response.var_loss_percent ?? null,
        }
  ));
};

/** Fetch timeseries data quality metrics (gaps, duplicates, outliers) per cached position. */
export const getDataQualityTimeseries = async (
  opts: {
    ticker?: string;
    exchange?: string;
    gapThresholdDays?: number;
    outlierSigma?: number;
    rollingWindow?: number;
  } = {},
): Promise<DataQualityTimeseriesResponse> => {
  const params = new URLSearchParams();
  if (opts.ticker) params.set("ticker", opts.ticker);
  if (opts.exchange) params.set("exchange", opts.exchange);
  if (opts.gapThresholdDays != null)
    params.set("gap_threshold_days", String(opts.gapThresholdDays));
  if (opts.outlierSigma != null)
    params.set("outlier_sigma", String(opts.outlierSigma));
  if (opts.rollingWindow != null)
    params.set("rolling_window", String(opts.rollingWindow));
  const qs = params.toString();
  return dataQualityTimeseriesContractSchema.parse(
    await fetchJson<DataQualityTimeseriesResponse>(
      `${API_BASE}/data-quality/timeseries${qs ? `?${qs}` : ""}`,
    ),
  );
};

// ───────────── Data Quality Admin API (read-write) ─────────────

export interface DataQualityIssue {
  id: string;
  type: string;
  severity: "high" | "medium" | "low";
  entity: Record<string, unknown>;
  description: string;
  suggested_fix: string;
  preview: Record<string, unknown>;
  fixable: boolean;
}

export interface DataQualityIssuesResponse {
  count: number;
  issues: DataQualityIssue[];
}

export interface DataQualityAuditEntry {
  id: string;
  timestamp: string;
  action: string;
  issue_id: string;
  entity: Record<string, unknown>;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  actor: string | null;
}

export interface DataQualityAuditResponse {
  count: number;
  entries: DataQualityAuditEntry[];
}

export interface DataQualityFixResult {
  status: string;
  ticker?: string;
  rows?: number;
  removed?: number;
  audit_id?: string;
}

export interface DataQualityBatchFixResponse {
  applied: number;
  failed: number;
  results: Array<{ issue_id: string; status: string; detail?: string } & DataQualityFixResult>;
}

export const getDataQualityIssues = async (filters: {
  type?: string;
  severity?: string;
  owner?: string;
  account?: string;
  ticker?: string;
} = {}): Promise<DataQualityIssuesResponse> => {
  const params = new URLSearchParams();
  if (filters.type) params.set("type", filters.type);
  if (filters.severity) params.set("severity", filters.severity);
  if (filters.owner) params.set("owner", filters.owner);
  if (filters.account) params.set("account", filters.account);
  if (filters.ticker) params.set("ticker", filters.ticker);
  const qs = params.toString();
  return dataQualityIssuesContractSchema.parse(
    await fetchJson<DataQualityIssuesResponse>(
      `${API_BASE}/data-quality/issues${qs ? `?${qs}` : ""}`,
    ),
  );
};

export const getDataQualityIssuePreview = async (
  issueId: string,
): Promise<DataQualityIssue> => {
  return fetchJson<DataQualityIssue>(
    `${API_BASE}/data-quality/issues/${encodeURIComponent(issueId)}/preview`,
  );
};

export const fixDataQualityIssue = async (
  issueId: string,
): Promise<DataQualityFixResult> => {
  return fetchJson<DataQualityFixResult>(
    `${API_BASE}/data-quality/issues/${encodeURIComponent(issueId)}/fix`,
    { method: "POST" },
  );
};

export const fixDataQualityBatch = async (
  issueIds: string[],
): Promise<DataQualityBatchFixResponse> => {
  return fetchJson<DataQualityBatchFixResponse>(`${API_BASE}/data-quality/fixes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ issue_ids: issueIds }),
  });
};

export const dedupeDataQualitySeries = async (
  ticker: string,
  exchange: string,
): Promise<DataQualityFixResult> => {
  return fetchJson<DataQualityFixResult>(
    `${API_BASE}/data-quality/series/${encodeURIComponent(ticker)}/${encodeURIComponent(exchange)}/dedupe`,
    { method: "POST" },
  );
};

export const getDataQualityAudit = async (
  limit?: number,
): Promise<DataQualityAuditResponse> => {
  const qs = limit != null ? `?limit=${limit}` : "";
  return dataQualityAuditContractSchema.parse(
    await fetchJson<DataQualityAuditResponse>(
      `${API_BASE}/data-quality/audit${qs}`,
    ),
  );
};

export const undoDataQualityAudit = async (
  entryId: string,
): Promise<{ status: string; entry_id: string }> => {
  return fetchJson<{ status: string; entry_id: string }>(
    `${API_BASE}/data-quality/audit/${encodeURIComponent(entryId)}/undo`,
    { method: "POST" },
  );
};

// ───────────── Goals API ─────────────
export interface Goal {
  name: string;
  target_amount: number;
  target_date: string;
}

export const getGoals = () => fetchJson<Goal[]>(`${API_BASE}/goals`);

export const createGoal = (goal: Goal) =>
  fetchJson<Goal>(`${API_BASE}/goals`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(goal),
  });

export const getGoal = (name: string, current: number) =>
  fetchJson<Goal & { progress: number; trades: any[] }>(
    `${API_BASE}/goals/${encodeURIComponent(name)}?current_amount=${current}`,
  );

export const updateGoal = (name: string, goal: Goal) =>
  fetchJson<Goal>(`${API_BASE}/goals/${encodeURIComponent(name)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(goal),
  });

export const deleteGoal = (name: string) =>
  fetchJson<{ status: string }>(`${API_BASE}/goals/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });

// ───────────── Tax API ─────────────
export const harvestTax = (
  positions: { ticker: string; basis: number; price: number }[],
  threshold = 0,
) =>
  fetchJson<{ trades: any[] }>(`${API_BASE}/tax/harvest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ positions, threshold }),
  });

// ───────────── Allowance Tracker ─────────────
export const getAllowances = (owner?: string) => {
  const suffix = owner ? `?owner=${encodeURIComponent(owner)}` : "";
  return fetchJson<{
    owner: string;
    tax_year: string;
    allowances: Record<string, { used: number; limit: number; remaining: number }>;
  }>(`${API_BASE}/tax/allowances${suffix}`);
};

// ───────────── Pension Forecast ─────────────
export interface PensionIncomeBreakdown {
  state_pension_annual?: number | null;
  defined_benefit_annual?: number | null;
  defined_contribution_annual?: number | null;
}

export interface PensionForecastResponse {
  forecast: { age: number; income: number }[];
  projected_pot_gbp: number;
  pension_pot_gbp: number;
  current_age: number;
  retirement_age: number;
  dob: string;
  earliest_retirement_age: number | null;
  retirement_income_breakdown?: PensionIncomeBreakdown | null;
  retirement_income_total_annual?: number | null;
  state_pension_annual?: number | null;
  contribution_annual?: number | null;
  desired_income_annual?: number | null;
  annuity_multiple_used?: number | null;
}

export const getPensionForecast = ({
  owner,
  deathAge,
  statePensionAnnual,
  contributionAnnual,
  contributionMonthly,
  desiredIncomeAnnual,
  investmentGrowthPct,
}: {
  owner: string;
  deathAge: number;
  statePensionAnnual?: number;
  contributionAnnual?: number;
  contributionMonthly?: number;
  desiredIncomeAnnual?: number;
  investmentGrowthPct?: number;
}) => {
  const params = new URLSearchParams({
    owner,
    death_age: String(deathAge),
  });
  if (statePensionAnnual !== undefined) {
    params.set("state_pension_annual", String(statePensionAnnual));
  }
  if (contributionAnnual !== undefined) {
    params.set("contribution_annual", String(contributionAnnual));
  }
  if (contributionMonthly !== undefined) {
    params.set("contribution_monthly", String(contributionMonthly));
  }
  if (desiredIncomeAnnual !== undefined) {
    params.set("desired_income_annual", String(desiredIncomeAnnual));
  }
  if (investmentGrowthPct !== undefined) {
    params.set("investment_growth_pct", String(investmentGrowthPct));
  }
  return fetchJson<PensionForecastResponse>(
    `${API_BASE}/pension/forecast?${params.toString()}`,
  );
};

// ───────────── Quests API ─────────────
export const getQuests = () =>
  fetchJson<QuestResponse>(`${API_BASE}/quests/today`);

export const completeQuest = (id: string) =>
  fetchJson<QuestResponse>(`${API_BASE}/quests/${encodeURIComponent(id)}/complete`, {
    method: "POST",
  });

// ───────────── Trail tasks API ─────────────
export const getTrailTasks = () =>
  fetchJson<TrailResponse>(`${API_BASE}/trail`);

export const completeTrailTask = (id: string) =>
  fetchJson<TrailResponse>(`${API_BASE}/trail/${encodeURIComponent(id)}/complete`, {
    method: "POST",
  });

// ───────────── Analytics ─────────────
export const logAnalyticsEvent = (payload: AnalyticsEventPayload) =>
  fetchJson<{ status: string }>(`${API_BASE}/analytics/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(() => undefined);

export const getAnalyticsFunnel = (source: AnalyticsSource) =>
  fetchJson<AnalyticsFunnelSummary>(`${API_BASE}/analytics/funnels/${source}`);

// ───────────── Support tools ─────────────
export interface Finding {
  level: "info" | "warning" | "error";
  message: string;
  suggestion?: string;
}

export const checkPortfolioHealth = () =>
  fetchJson<{ findings: Finding[] }>(
    `${API_BASE}/support/portfolio-health`,
    { method: "POST" },
  );

/**
 * Fetch recent backend log output for the Support page's Logs panel.
 *
 * Routed through the authenticated {@link fetchText} path (not a raw
 * `fetch`) so it attaches the Cognito bearer token — otherwise API Gateway's
 * Cognito authorizer rejects the request with 401 before it ever reaches the
 * Lambda on AWS deployments (#6111). `GET /logs` returns `PlainTextResponse`,
 * so this uses fetchText rather than fetchJson.
 */
export const getLogs = () => fetchText(`${API_BASE}/logs`);

// ───────────── Account signup ─────────────
export interface AccountSignupRequest {
  name: string;
  email: string;
  note?: string;
}

export interface AccountSignupResponse {
  status: string;
}

/** Submit a public account-creation request for admin approval. */
export const requestAccountSignup = (payload: AccountSignupRequest) =>
  fetchJson<AccountSignupResponse>(`${API_BASE}/signup/request`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

// ───────────── Portfolio accounts ─────────────
export interface AccountCreateRequest {
  owner: string;
  account_type: string;
  currency?: string;
}

export interface AccountCreateResponse {
  status: string;
  owner: string;
  account: string;
  currency: string;
}

/** Create a new, empty portfolio account (e.g. ISA, SIPP) for an owner. */
export const createAccount = (payload: AccountCreateRequest) =>
  fetchJson<AccountCreateResponse>(`${API_BASE}/accounts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

// ───────────── Holdings CSV import ─────────────
export interface ImportHoldingsCsvResponse {
  path: string;
}

export interface ReconciledHolding {
  ticker: string;
  units: number;
  value_gbp: number;
}

export interface ReconciledQuantityChange {
  ticker: string;
  stored_units: number;
  imported_units: number;
  delta: number;
}

export interface ReconciledValueChange {
  ticker: string;
  stored_value_gbp: number;
  imported_value_gbp: number;
  delta_gbp: number;
}

export interface ReconcileHoldingsCsvResponse {
  added: ReconciledHolding[];
  removed: ReconciledHolding[];
  quantity_changed: ReconciledQuantityChange[];
  value_changed: ReconciledValueChange[];
  cash_balance: {
    stored_gbp: number;
    imported_gbp: number;
    delta_gbp: number;
  };
}

const createHoldingsCsvFormData = (
  owner: string,
  account: string,
  provider: string,
  file: File,
) => {
  const formData = new FormData();
  formData.append("owner", owner);
  formData.append("account", account);
  formData.append("provider", provider);
  formData.append("file", file);
  return formData;
};

/** Preview how a CSV differs from stored holdings without applying changes. */
export const reconcileHoldingsCsv = (
  owner: string,
  account: string,
  provider: string,
  file: File,
): Promise<ReconcileHoldingsCsvResponse> =>
  fetchJson<ReconcileHoldingsCsvResponse>(`${API_BASE}/holdings/reconcile`, {
    method: "POST",
    body: createHoldingsCsvFormData(owner, account, provider, file),
  });

/**
 * Upload a CSV export of holdings/transactions for `owner`/`account` and have
 * the backend parse it with the given `provider` and persist the result.
 */
export const importHoldingsCsv = (
  owner: string,
  account: string,
  provider: string,
  file: File,
): Promise<ImportHoldingsCsvResponse> =>
  fetchJson<ImportHoldingsCsvResponse>(`${API_BASE}/holdings/import`, {
    method: "POST",
    body: createHoldingsCsvFormData(owner, account, provider, file),
  });

// Chat (tool-calling agent over the MCP data-query server)

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

/**
 * Send one chat turn to the backend's Bedrock tool-calling agent. `history`
 * is resent in full each call -- there is no server-side session/persistence
 * yet, so the caller owns the running conversation.
 */
export const postChat = (
  message: string,
  history: ChatMessage[] = [],
): Promise<{ reply: string }> =>
  fetchJson<{ reply: string }>(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
  });
