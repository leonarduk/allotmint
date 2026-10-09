import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  DEFAULT_API_BASE,
  API_BASE,
  createClient,
  fetchJson,
  fetchText,
  getLogs,
  setAuthToken,
  setApiBase,
  login,
  subscribeNudges,
  getEvents,
  runScenario,
  getPortfolio,
  getPensionForecast,
  getConfig,
  getTradingPageData,
  getTrendWatchLatest,
  UNAUTHORIZED_EVENT,
  reconcileHoldingsCsv,
  importHoldingsCsv,
  runCustomQuery,
  getCachedGroupInstruments,
  clearGroupInstrumentCache,
  checkScreenerAvailable,
  getChatConversation,
  putChatConversation,
  archiveChatConversation,
  deleteChatHistory,
  getAlphaVsBenchmark,
  getTrackingError,
  getGroupAlphaVsBenchmark,
  getGroupTrackingError,
  getGroupCurrencyContributions,
  getOwnerCurrencyContributions,
  getGroupLookThrough,
  getOwnerLookThrough,
  getInstrumentAllocation,
  refreshInstrumentLookThrough,
} from "@/api";
import {
  clearFetchCache,
  readFetchCache,
  writeFetchCache,
} from "@/utils/fetchCache";
import {
  appendChatMessage,
  getChatIdentityEpoch,
  getChatMessages,
  getChatSyncState,
  setChatSyncState,
  startNewChat,
} from "@/utils/chatConversation";
import { onAuthChange } from "@/authEvents";

const csvFile = new File(["ticker,units"], "holdings.csv", {
  type: "text/csv",
});

describe("holdings CSV reconciliation", () => {
  beforeEach(() => {
    localStorage.clear();
    setAuthToken(null);
    setApiBase(DEFAULT_API_BASE);
  });

  it("posts multipart fields to the read-only reconciliation endpoint", async () => {
    const response = {
      added: [],
      removed: [],
      quantity_changed: [],
      value_changed: [],
      cash_balance: { stored_gbp: 1, imported_gbp: 2, delta_gbp: 1 },
    };
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(response),
    });
    global.fetch = mockFetch;

    await expect(
      reconcileHoldingsCsv("alice", "ISA", "degiro", csvFile),
    ).resolves.toEqual(response);

    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${DEFAULT_API_BASE}/holdings/reconcile`);
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    const body = init.body as FormData;
    expect(body.get("owner")).toBe("alice");
    expect(body.get("account")).toBe("ISA");
    expect(body.get("provider")).toBe("degiro");
    expect(body.get("file")).toBe(csvFile);
    // No explicit Content-Type: the browser must set the multipart boundary itself.
    const headers = init.headers as Headers;
    expect(headers.has("Content-Type")).toBe(false);
  });

  it("routes through the authenticated client, attaching the bearer token", async () => {
    setAuthToken("token123");
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          added: [],
          removed: [],
          quantity_changed: [],
          value_changed: [],
          cash_balance: { stored_gbp: 0, imported_gbp: 0, delta_gbp: 0 },
        }),
    });
    global.fetch = mockFetch;

    await reconcileHoldingsCsv("alice", "ISA", "degiro", csvFile);

    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer token123");
  });

  it("dispatches UNAUTHORIZED_EVENT and rejects on a 401 response", async () => {
    const handler = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, handler);
    try {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        statusText: "Unauthorized",
        json: () => Promise.resolve({ detail: "Session expired" }),
      });
      global.fetch = mockFetch;

      await expect(
        reconcileHoldingsCsv("alice", "ISA", "degiro", csvFile),
      ).rejects.toThrow("Session expired");
      expect(handler).toHaveBeenCalledTimes(1);
    } finally {
      window.removeEventListener(UNAUTHORIZED_EVENT, handler);
    }
  });
});

describe("holdings CSV import", () => {
  beforeEach(() => {
    localStorage.clear();
    setAuthToken(null);
    setApiBase(DEFAULT_API_BASE);
  });

  it("posts multipart fields to the import endpoint", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ path: "/data/accounts/alice/ISA.json" }),
    });
    global.fetch = mockFetch;

    await expect(
      importHoldingsCsv("alice", "ISA", "degiro", csvFile),
    ).resolves.toEqual({ path: "/data/accounts/alice/ISA.json" });

    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${DEFAULT_API_BASE}/holdings/import`);
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    const body = init.body as FormData;
    expect(body.get("owner")).toBe("alice");
    expect(body.get("account")).toBe("ISA");
    expect(body.get("provider")).toBe("degiro");
    expect(body.get("file")).toBe(csvFile);
  });

  it("dispatches UNAUTHORIZED_EVENT and rejects on a 401 response", async () => {
    const handler = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, handler);
    try {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        statusText: "Unauthorized",
        json: () => Promise.resolve({ detail: "Session expired" }),
      });
      global.fetch = mockFetch;

      await expect(
        importHoldingsCsv("alice", "ISA", "degiro", csvFile),
      ).rejects.toThrow("Session expired");
      expect(handler).toHaveBeenCalledTimes(1);
    } finally {
      window.removeEventListener(UNAUTHORIZED_EVENT, handler);
    }
  });
});

describe("auth token handling", () => {
  beforeEach(() => {
    localStorage.clear();
    setAuthToken(null);
    setApiBase(DEFAULT_API_BASE);
  });

  it("stores token in localStorage and adds header", async () => {
    setAuthToken("token123");
    expect(localStorage.getItem("authToken")).toBe("token123");
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;
    await fetchJson("/foo");
    expect(mockFetch).toHaveBeenCalled();
    const args = mockFetch.mock.calls[0];
    const headers = args[1].headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer token123");
  });
});

describe("unauthorized event (issue #4674)", () => {
  beforeEach(() => {
    localStorage.clear();
    setAuthToken(null);
    setApiBase(DEFAULT_API_BASE);
  });

  it("dispatches UNAUTHORIZED_EVENT and still rejects on a 401 response", async () => {
    const handler = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, handler);
    try {
      const mockFetch = vi
        .fn()
        .mockResolvedValue({ ok: false, status: 401, statusText: "Unauthorized" });
      // @ts-expect-error: replacing global fetch with mock
      global.fetch = mockFetch;
      await expect(fetchJson("/owners")).rejects.toThrow("HTTP 401");
      expect(handler).toHaveBeenCalledTimes(1);
    } finally {
      window.removeEventListener(UNAUTHORIZED_EVENT, handler);
    }
  });

  it("does not dispatch UNAUTHORIZED_EVENT for other error statuses", async () => {
    const handler = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, handler);
    try {
      const mockFetch = vi
        .fn()
        .mockResolvedValue({ ok: false, status: 500, statusText: "Server Error" });
      // @ts-expect-error: replacing global fetch with mock
      global.fetch = mockFetch;
      await expect(fetchJson("/owners")).rejects.toThrow("HTTP 500");
      expect(handler).not.toHaveBeenCalled();
    } finally {
      window.removeEventListener(UNAUTHORIZED_EVENT, handler);
    }
  });

  it("surfaces the backend's `detail` message instead of a bare status (issue #6058)", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      json: () =>
        Promise.resolve({
          detail:
            "No local login override is configured. Go to Support -> Local login override and select a user to continue in local/demo mode.",
        }),
    });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;
    await expect(fetchJson("/data-explorer/tree")).rejects.toThrow(
      "Go to Support -> Local login override",
    );
  });

  it("falls back to the generic status message when the error body isn't JSON", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Server Error",
      json: () => Promise.reject(new Error("not json")),
    });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;
    await expect(fetchJson("/owners")).rejects.toThrow("HTTP 500");
  });
});

describe("transient backend failures (issue #6193)", () => {
  it("retries transient failures for safe requests", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 503, statusText: "Service Unavailable" })
      .mockResolvedValueOnce({ ok: true, status: 200, json: () => Promise.resolve({ ok: true }) });
    const { fetchJson: testFetchJson } = createClient(
      "http://localhost:6468",
      null,
      mockFetch as unknown as typeof fetch,
      { transientRetryDelaysMs: [0] },
    );

    await expect(testFetchJson("/portfolio-group/all/regions")).resolves.toEqual({ ok: true });
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("shows a user-friendly message after transient retries are exhausted", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      statusText: "Service Unavailable",
      json: () => Promise.resolve({ message: "Service Unavailable" }),
    });
    const { fetchJson: testFetchJson } = createClient(
      "http://localhost:6468",
      null,
      mockFetch as unknown as typeof fetch,
      { transientRetryDelaysMs: [0, 0] },
    );

    await expect(testFetchJson("/compliance/alex")).rejects.toMatchObject({
      message: "The backend service is temporarily unavailable. Please try again.",
      status: 503,
    });
    expect(mockFetch).toHaveBeenCalledTimes(3);
  });

  it("does not retry unsafe requests", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      statusText: "Service Unavailable",
      json: () => Promise.resolve({}),
    });
    const { fetchJson: testFetchJson } = createClient(
      "http://localhost:6468",
      null,
      mockFetch as unknown as typeof fetch,
      { transientRetryDelaysMs: [0, 0] },
    );

    await expect(testFetchJson("/trades", { method: "POST" })).rejects.toThrow(
      "temporarily unavailable",
    );
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });
});

describe("getCachedGroupInstruments cache eviction on rejection (issue #7222)", () => {
  // Regression test: getCachedGroupInstruments memoizes its promise by cache
  // key BEFORE the request settles. If a request fails and the rejected
  // promise is left cached, every subsequent caller (including a user
  // clicking "Retry" in CustomQuery) replays the SAME rejection forever,
  // with no new network request — only a full page reload (which resets the
  // module-level cache) recovers. This exercises the real cache in @/api
  // directly, not a mocked module, so it fails if the eviction-on-error path
  // regresses even though a caller-side test with a mocked "@/api" module
  // would stay green.
  beforeEach(() => {
    setApiBase(DEFAULT_API_BASE);
    clearGroupInstrumentCache();
  });

  afterEach(() => {
    clearGroupInstrumentCache();
  });

  it("evicts a rejected entry so a second call issues a new request instead of replaying the failure", async () => {
    const mockFetch = vi
      .fn()
      .mockRejectedValueOnce(new Error("network down"))
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve([
            { ticker: "PFE", name: "Pfizer", units: 1, market_value_gbp: 1, gain_gbp: 1 },
          ]),
      });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await expect(getCachedGroupInstruments("all")).rejects.toThrow("network down");
    expect(mockFetch).toHaveBeenCalledTimes(1);

    // A second call after the failure must hit the network again, not
    // replay the cached rejection.
    const rows = await getCachedGroupInstruments("all");
    expect(rows).toEqual([
      { ticker: "PFE", name: "Pfizer", units: 1, market_value_gbp: 1, gain_gbp: 1 },
    ]);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });
});

describe("HTTP error shape relied on by ChatPanel (#7721)", () => {
  it("carries the body's machine-readable code on the thrown error", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      statusText: "Bad Gateway",
      json: () => Promise.resolve({ detail: "backend detail", code: "mcp_unreachable" }),
    });
    const { fetchJson: testFetchJson } = createClient(
      "http://localhost:6468",
      null,
      mockFetch as unknown as typeof fetch,
    );

    await expect(testFetchJson("/chat", { method: "POST" })).rejects.toMatchObject({
      status: 502,
      code: "mcp_unreachable",
      message: expect.stringMatching(/temporarily unavailable/i),
    });
  });

  it.each([400, 429, 502, 503])("rejects a POST /chat %i with the response status attached", async (status) => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status,
      statusText: "Error",
      json: () => Promise.resolve({ detail: "backend detail" }),
    });
    const { fetchJson: testFetchJson } = createClient(
      "http://localhost:6468",
      null,
      mockFetch as unknown as typeof fetch,
    );

    await expect(testFetchJson("/chat", { method: "POST" })).rejects.toMatchObject({ status, code: undefined });
    // POSTs are not retried, so a 502/503 surfaces after one attempt.
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });
});

describe("stalled-request timeout (issue #7074)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("aborts a request that never settles and surfaces a friendly timeout error instead of hanging forever", async () => {
    // Simulates the exact symptom from #7074: GET /portfolio-group/all/instruments
    // and GET /instrument/admin/groupings were observed to hang with no status
    // and no failure. Like the real fetch() implementation, this mock only
    // settles once its AbortSignal fires — proving the fix is what unsticks it,
    // not some incidental rejection from the mock itself.
    const mockFetch = vi.fn((_url: string, init?: RequestInit) => {
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("Aborted", "AbortError"));
        });
      });
    });
    const { fetchJson: testFetchJson } = createClient(
      "http://localhost:6468",
      null,
      mockFetch as unknown as typeof fetch,
      { fetchTimeoutMs: 5000 },
    );

    const pending = testFetchJson("/portfolio-group/all/instruments");
    const assertion = expect(pending).rejects.toMatchObject({
      message: expect.stringMatching(/timed out/i),
    });

    await vi.advanceTimersByTimeAsync(5000);
    await assertion;

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const requestInit = mockFetch.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(requestInit?.signal?.aborted).toBe(true);
  });

  it("does not time out a request that resolves comfortably before the deadline", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ ok: true }),
    });
    const { fetchJson: testFetchJson } = createClient(
      "http://localhost:6468",
      null,
      mockFetch as unknown as typeof fetch,
      { fetchTimeoutMs: 5000 },
    );

    await expect(testFetchJson("/owners")).resolves.toEqual({ ok: true });
  });

  it("still propagates a caller-initiated abort (e.g. component unmount) without relabeling it as a timeout", async () => {
    const controller = new AbortController();
    const mockFetch = vi.fn((_url: string, init?: RequestInit) => {
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          const err = new DOMException("Aborted", "AbortError");
          reject(err);
        });
      });
    });
    const { fetchJson: testFetchJson } = createClient(
      "http://localhost:6468",
      null,
      mockFetch as unknown as typeof fetch,
      { fetchTimeoutMs: 5000 },
    );

    const pending = testFetchJson("/owners", { signal: controller.signal });
    const assertion = expect(pending).rejects.toMatchObject({ name: "AbortError" });

    controller.abort();
    await assertion;
  });

  it("lets one request override the client-wide timeout (slow chat turns, #7874)", async () => {
    const mockFetch = vi.fn((_url: string, init?: RequestInit) => {
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("Aborted", "AbortError"));
        });
      });
    });
    const { fetchJson: testFetchJson } = createClient(
      "http://localhost:6468",
      null,
      mockFetch as unknown as typeof fetch,
      { fetchTimeoutMs: 5000 },
    );

    const pending = testFetchJson("/chat", { method: "POST" }, 20000);
    // ChatPanel keys its timeout message off `timeout: true` (#7721).
    const assertion = expect(pending).rejects.toMatchObject({
      message: expect.stringMatching(/timed out after 20s/i),
      timeout: true,
    });

    await vi.advanceTimersByTimeAsync(5000);
    const requestInit = mockFetch.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(requestInit?.signal?.aborted).toBe(false);

    await vi.advanceTimersByTimeAsync(15000);
    await assertion;
  });
});

describe("fetchText / getLogs (issue #6111)", () => {
  beforeEach(() => {
    localStorage.clear();
    setAuthToken(null);
    setApiBase(DEFAULT_API_BASE);
  });

  it("parses the response body as text rather than JSON", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, text: () => Promise.resolve("log line one\nlog line two") });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;
    const text = await fetchText("/logs");
    expect(text).toBe("log line one\nlog line two");
  });

  it("attaches the Authorization header, same as fetchJson", async () => {
    setAuthToken("logs-token");
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, text: () => Promise.resolve("") });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;
    await getLogs();
    const args = mockFetch.mock.calls[0];
    expect(args[0]).toBe(`${API_BASE}/logs`);
    const headers = args[1].headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer logs-token");
  });

  it("dispatches UNAUTHORIZED_EVENT and rejects with the backend detail on a 401", async () => {
    const handler = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, handler);
    try {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        statusText: "Unauthorized",
        json: () => Promise.resolve({ detail: "Session expired" }),
      });
      // @ts-expect-error: replacing global fetch with mock
      global.fetch = mockFetch;
      await expect(fetchText("/logs")).rejects.toThrow("Session expired");
      expect(handler).toHaveBeenCalledTimes(1);
    } finally {
      window.removeEventListener(UNAUTHORIZED_EVENT, handler);
    }
  });
});

describe("login", () => {
  beforeEach(() => {
    localStorage.clear();
    setAuthToken(null);
    setApiBase(DEFAULT_API_BASE);
  });

  it("succeeds for allowed tokens", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ access_token: "abc" }),
      });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;
    const token = await login("good-id-token");
    expect(token).toBe("abc");
    expect(localStorage.getItem("authToken")).toBe("abc");
    expect(mockFetch).toHaveBeenCalledWith(`${API_BASE}/token`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ id_token: "good-id-token" }),
    });
  });

  it("rejects disallowed tokens", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: false, status: 400, statusText: "Bad" });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;
    await expect(login("bad-id-token")).rejects.toThrow("Login failed");
  });
});

describe("nudge subscriptions", () => {
  beforeEach(() => {
    setApiBase(DEFAULT_API_BASE);
  });

  it("clamps frequency within bounds", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;
    await subscribeNudges("bob", 0);
    let args = mockFetch.mock.calls[0];
    expect(args[0]).toBe(`${API_BASE}/nudges/subscribe`);
    expect(args[1].body).toBe(JSON.stringify({ user: "bob", frequency: 1 }));
    expect((args[1].headers as Headers).get("Content-Type")).toBe(
      "application/json",
    );
    await subscribeNudges("bob", 40);
    args = mockFetch.mock.calls[1];
    expect(args[1].body).toBe(JSON.stringify({ user: "bob", frequency: 30 }));
  });
});

describe("runtime api base", () => {
  beforeEach(() => {
    setApiBase(DEFAULT_API_BASE);
  });

  it("supports runtime API base overrides", async () => {
    setApiBase("https://example.com///");
    expect(API_BASE).toBe("https://example.com");

    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await fetchJson("/health");
    expect(mockFetch).toHaveBeenCalledWith(
      "https://example.com/health",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });
});

describe("portfolio holdings", () => {
  it("passes through stale price metadata", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          owner: "alice",
          as_of: "2024-01-01",
          trades_this_month: 0,
          trades_remaining: 0,
          total_value_estimate_gbp: 0,
          accounts: [
            {
              account_type: "general",
              currency: "GBP",
              value_estimate_gbp: 0,
              holdings: [
                {
                  ticker: "AAA",
                  name: "Alpha",
                  units: 1,
                  acquired_date: "2024-01-01",
                  current_price_gbp: 100,
                  current_price_currency: "GBP",
                  last_price_date: "2024-01-01",
                  last_price_time: "2024-01-01T10:00:00Z",
                  is_stale: true,
                },
              ],
            },
          ],
        }),
    });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;
    const data = await getPortfolio("alice");
    const holding = data.accounts[0].holdings[0];
    expect(holding.last_price_time).toBe("2024-01-01T10:00:00Z");
    expect(holding.is_stale).toBe(true);
  });
});

describe("contract validation", () => {
  it("rejects invalid config responses", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({ app_env: 123 }) });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await expect(getConfig()).rejects.toThrow();
  });
});

describe("scenario APIs", () => {
  it("fetches events", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;
    await getEvents();
    expect(mockFetch).toHaveBeenCalledWith(
      `${API_BASE}/events`,
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });

  it("runs scenario with proper query params", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;
    await runScenario({ event_id: "e1", horizons: ["1d", "1w"] });
    const url =
      `${API_BASE}/scenario/historical?event_id=e1&horizons=1d%2C1w`;
    expect(mockFetch).toHaveBeenCalledWith(
      url,
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });
});

describe("custom query (issue #7104)", () => {
  const QUERY_PARAMS = {
    start: "2024-01-01",
    end: "2024-02-01",
    owners: ["alex"],
    tickers: ["AAA.L"],
    metrics: ["meta"],
  };

  it("propagates a 404 error with the backend's detail message instead of unwrapping a results envelope", async () => {
    // Regression guard for PR #7133: a 404 from /custom-query/run can mean
    // "invalid query parameters", not just "saved query not found".  The
    // backend's detail must reach the caller verbatim so the UI can show the
    // real reason rather than a misleading generic message.
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: "Not Found",
      json: () => Promise.resolve({ detail: "Unknown metric: bogus" }),
    });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await expect(runCustomQuery(QUERY_PARAMS)).rejects.toMatchObject({
      status: 404,
      message: "Unknown metric: bogus",
    });

    // The error path must not attempt to read a {results} envelope.
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("keeps the 'Query not found' wording for a 404 saved-query miss", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: "Not Found",
      json: () => Promise.resolve({ detail: "Query not found" }),
    });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await expect(runCustomQuery(QUERY_PARAMS)).rejects.toMatchObject({
      status: 404,
      message: "Query not found",
    });
  });

  it("surfaces a distinct message for a 400 validation failure (not 'Query not found')", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      json: () => Promise.resolve({ detail: "Unknown metric: bogus" }),
    });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await expect(runCustomQuery(QUERY_PARAMS)).rejects.toMatchObject({
      status: 400,
      message: expect.stringMatching(/Invalid query parameters.*Unknown metric/),
    });
  });

  it("propagates a 500 error with the backend's detail message", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: () => Promise.resolve({ detail: "Query engine crashed" }),
    });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await expect(runCustomQuery(QUERY_PARAMS)).rejects.toMatchObject({
      status: 500,
      message: expect.stringMatching(/Failed to run query.*Query engine crashed/),
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("falls back to the HTTP status when the error body is not JSON", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: () => Promise.reject(new Error("not json")),
    });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await expect(runCustomQuery(QUERY_PARAMS)).rejects.toThrow("HTTP 500");

    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("preserves the original error on `cause` and keeps status/code for callers", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      statusText: "Unprocessable Entity",
      json: () => Promise.resolve({ detail: "bad range", code: "bad_range" }),
    });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    const err = await runCustomQuery(QUERY_PARAMS).catch((e) => e);
    expect(err).toMatchObject({ status: 422, code: "bad_range" });
    expect((err as Error).cause).toBeInstanceOf(Error);
    expect(((err as Error).cause as Error).message).toBe("bad range");
  });

  it("reports a failure with no HTTP status (network error) as 'Failed to run query'", async () => {
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = vi.fn().mockRejectedValue(new Error("network down"));

    const err = await runCustomQuery(QUERY_PARAMS).catch((e) => e);
    expect((err as Error).message).toBe("Failed to run query: network down");
    expect((err as { status?: number }).status).toBeUndefined();
  });
});

describe("client-side request forgery guard (CodeQL #218)", () => {
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    setApiBase(DEFAULT_API_BASE);
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    setApiBase(DEFAULT_API_BASE);
  });

  it("blocks an absolute URL targeting a different host", async () => {
    const mockFetch = vi.fn();
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;
    await expect(
      fetchJson("http://attacker.example.com/steal"),
    ).rejects.toThrow("Blocked request to unexpected host");
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("allows an absolute URL whose origin matches the configured API base", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;
    await fetchJson(`${DEFAULT_API_BASE}/health`);
    expect(mockFetch).toHaveBeenCalledWith(
      `${DEFAULT_API_BASE}/health`,
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });

  it("allows a relative path which resolves to the configured API host", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;
    await fetchJson("/health");
    expect(mockFetch).toHaveBeenCalledWith(
      `${DEFAULT_API_BASE}/health`,
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });

  it("still blocks after setApiBase changes the origin", async () => {
    setApiBase("https://api.example.com");
    const mockFetch = vi.fn();
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;
    await expect(
      fetchJson("http://attacker.example.com/steal"),
    ).rejects.toThrow("Blocked request to unexpected host");
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("throws a clear error when the configured API base is not a valid absolute URL", async () => {
    // setApiBase() now validates eagerly, so the error is thrown there rather
    // than deferred to fetchJson().  Test both that setApiBase rejects the bad
    // value and that createClient with the same bad base also rejects fetchJson.
    expect(() => setApiBase("not-a-valid-url")).toThrow("Invalid API base URL");

    const { fetchJson: testFetchJson } = createClient("not-a-valid-url");
    await expect(testFetchJson("/health")).rejects.toThrow(
      "API base is not a valid absolute URL",
    );
  });

  it("throws a clear error when resolveBase() returns an empty string", async () => {
    // createClient with a static empty-string base exercises the same eager
    // URL-validation path as the misconfigured-API_BASE case above.
    const { fetchJson: testFetchJson } = createClient("");
    await expect(testFetchJson("/health")).rejects.toThrow(
      "API base is not a valid absolute URL",
    );
  });

  it("documents that a protocol-relative URL is prepended to the base (origin unchanged)", async () => {
    // "//evil.com/path" is not a valid absolute URL in Node/undici so new URL() throws,
    // landing in the catch branch which prepends the configured base.
    // The resulting fullUrl is "http://localhost:6468//evil.com/path" — origin is still
    // http://localhost:6468, so the SSRF guard passes.  This test pins that behaviour.
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;
    await fetchJson("//evil.com/path");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining(DEFAULT_API_BASE),
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });
});

describe("safe URL reconstruction (CodeQL #218 follow-up)", () => {
  it("rebuilds the request URL from the trusted base origin and validated path/query", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    const { fetchJson: testFetchJson } = createClient(
      "http://localhost:6468/api/v1",
      null,
      mockFetch as unknown as typeof fetch,
    );
    await testFetchJson("/holdings?owner=alice#section");
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:6468/api/v1/holdings?owner=alice#section",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });

  it("still blocks a same-origin path outside the configured prefix when reconstructing", async () => {
    const mockFetch = vi.fn();
    const { fetchJson: testFetchJson } = createClient(
      "http://localhost:6468/api/v1",
      null,
      mockFetch as unknown as typeof fetch,
    );
    await expect(
      testFetchJson("http://localhost:6468/other-app/steal?x=1"),
    ).rejects.toThrow("does not start with configured API base");
    expect(mockFetch).not.toHaveBeenCalled();
  });
});

describe("path-prefix guard (issue #3170)", () => {
  it("blocks a same-origin URL that does not match the configured API path prefix", async () => {
    const { fetchJson: testFetchJson } = createClient("http://localhost:6468/api/v1");
    await expect(
      testFetchJson("http://localhost:6468/other-app/steal"),
    ).rejects.toThrow("does not start with configured API base");
  });

  it("blocks a same-origin URL that shares the prefix string but is not within the prefix path", async () => {
    const { fetchJson: testFetchJson } = createClient("http://localhost:6468/api/v1");
    await expect(
      testFetchJson("http://localhost:6468/api/v1other"),
    ).rejects.toThrow("does not start with configured API base");
  });

  it("allows a same-origin absolute URL that starts with the configured API path prefix", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    const { fetchJson: testFetchJson } = createClient(
      "http://localhost:6468/api/v1",
      null,
      mockFetch as unknown as typeof fetch,
    );
    await testFetchJson("http://localhost:6468/api/v1/users");
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:6468/api/v1/users",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });

  it("allows a relative path that resolves under the configured API path prefix", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    const { fetchJson: testFetchJson } = createClient(
      "http://localhost:6468/api/v1",
      null,
      mockFetch as unknown as typeof fetch,
    );
    await testFetchJson("/users");
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:6468/api/v1/users",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });

  it("allows a URL that exactly equals the configured API base", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    const { fetchJson: testFetchJson } = createClient(
      "http://localhost:6468/api/v1",
      null,
      mockFetch as unknown as typeof fetch,
    );
    await testFetchJson("http://localhost:6468/api/v1");
    expect(mockFetch).toHaveBeenCalled();
  });

  it("allows a URL that equals the configured API base with query params appended", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    const { fetchJson: testFetchJson } = createClient(
      "http://localhost:6468/api/v1",
      null,
      mockFetch as unknown as typeof fetch,
    );
    await testFetchJson("http://localhost:6468/api/v1?filter=x");
    expect(mockFetch).toHaveBeenCalled();
  });

  it("normalises a trailing slash in the configured API base and still blocks wrong paths", async () => {
    const { fetchJson: testFetchJson } = createClient("http://localhost:6468/api/v1/");
    await expect(
      testFetchJson("http://localhost:6468/other-app/steal"),
    ).rejects.toThrow("does not start with configured API base");
  });

  it("normalises a trailing slash in the configured API base and still allows correct paths", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    const { fetchJson: testFetchJson } = createClient(
      "http://localhost:6468/api/v1/",
      null,
      mockFetch as unknown as typeof fetch,
    );
    await testFetchJson("http://localhost:6468/api/v1/users");
    expect(mockFetch).toHaveBeenCalled();
  });
});

describe("pension forecast", () => {
  it("passes investment growth pct", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            forecast: [],
            projected_pot_gbp: 0,
            current_age: 30,
            retirement_age: 65,
            dob: "1990-01-01",
            earliest_retirement_age: null,
          }),
      });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;
    await getPensionForecast({
      owner: "alex",
      deathAge: 90,
      investmentGrowthPct: 7,
    });
    const url = mockFetch.mock.calls[0][0] as string;
    expect(url).toContain("investment_growth_pct=7");
  });

  it("sets monthly contribution when provided", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            forecast: [],
            projected_pot_gbp: 0,
            current_age: 30,
            retirement_age: 65,
            dob: "1990-01-01",
            earliest_retirement_age: null,
          }),
      });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;
    await getPensionForecast({
      owner: "alex",
      deathAge: 90,
      contributionMonthly: 100,
    });
    const url = mockFetch.mock.calls[0][0] as string;
    expect(url).toContain("contribution_monthly=100");
    expect(url).not.toContain("contribution_annual");
  });
});

describe("trading page data", () => {
  it("fetches the signals report and settings and combines them", async () => {
    const signals = [{ ticker: "AAA", action: "BUY", reason: "r" }];
    const blocked = [{ ticker: "BBB", action: "SELL", reasons: ["alex: x"] }];
    const settings = {
      rsi_buy: 30,
      rsi_sell: 70,
      rsi_window: 14,
      ma_short_window: 20,
      ma_long_window: 50,
      pe_max: null,
      de_max: null,
      min_sharpe: null,
      max_volatility: null,
    };
    const mockFetch = vi.fn((url: string) =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve(
            url.endsWith("/trading-agent/settings")
              ? settings
              : { signals, blocked },
          ),
      }),
    );
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await expect(getTradingPageData()).resolves.toEqual({
      signals,
      blocked,
      settings,
    });

    const calledUrls = mockFetch.mock.calls.map(([url]) => url as string);
    expect(calledUrls).toContain(`${API_BASE}/trading-agent/signals/report`);
    expect(calledUrls).toContain(`${API_BASE}/trading-agent/settings`);
  });

  it("falls back to /trading-agent/signals when the report endpoint 404s", async () => {
    const signals = [{ ticker: "AAA", action: "BUY", reason: "r" }];
    const settings = { rsi_buy: 30 };
    const mockFetch = vi.fn((url: string) => {
      if (url.endsWith("/trading-agent/signals/report")) {
        return Promise.resolve({
          ok: false,
          status: 404,
          statusText: "Not Found",
          json: () => Promise.resolve({ detail: "Not Found" }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve(
            url.endsWith("/trading-agent/settings") ? settings : signals,
          ),
      });
    });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    const data = await getTradingPageData();

    expect(data).toEqual({ signals, settings });
    expect(data.blocked).toBeUndefined();
    const calledUrls = mockFetch.mock.calls.map(([url]) => url as string);
    expect(calledUrls).toContain(`${API_BASE}/trading-agent/signals`);
  });

  it("does not fall back when the report endpoint fails with a non-404", async () => {
    const mockFetch = vi.fn((url: string) =>
      Promise.resolve(
        url.endsWith("/trading-agent/signals/report")
          ? {
              ok: false,
              status: 500,
              statusText: "Internal Server Error",
              json: () => Promise.resolve({}),
            }
          : { ok: true, json: () => Promise.resolve({}) },
      ),
    );
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await expect(getTradingPageData()).rejects.toThrow();
    const calledUrls = mockFetch.mock.calls.map(([url]) => url as string);
    expect(calledUrls).not.toContain(`${API_BASE}/trading-agent/signals`);
  });

  it("rejects when either endpoint fails", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 503,
        statusText: "Service Unavailable",
      })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await expect(getTradingPageData()).rejects.toThrow();
  });
});

describe("getTrendWatchLatest", () => {
  it("returns null before the first run (404)", async () => {
    const mockFetch = vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 404,
        statusText: "Not Found",
        json: () => Promise.resolve({ detail: "No trend-watch report yet" }),
      }),
    );
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await expect(getTrendWatchLatest("alex")).resolves.toBeNull();
    expect(mockFetch.mock.calls[0][0]).toBe(
      `${API_BASE}/trend-watch/alex/latest`,
    );
  });

  it("rethrows any other failure", async () => {
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        json: () => Promise.resolve({}),
      }),
    );

    await expect(getTrendWatchLatest("alex")).rejects.toThrow();
  });
});

describe("checkScreenerAvailable", () => {
  beforeEach(() => {
    localStorage.clear();
    setAuthToken(null);
    setApiBase(DEFAULT_API_BASE);
  });

  it("returns false when the backend gates the screener behind a 402", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 402,
      statusText: "Payment Required",
      json: () =>
        Promise.resolve({
          detail:
            "Screener is not available: This feature requires the allotmint-pro package, which is not installed in this deployment. See https://github.com/leonarduk/allotmint-pro for upgrade options.",
        }),
    });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await expect(checkScreenerAvailable()).resolves.toBe(false);
  });

  it("returns true when the probe reaches ticker validation (400 = feature present)", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      json: () => Promise.resolve({ detail: "No tickers supplied" }),
    });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await expect(checkScreenerAvailable()).resolves.toBe(true);
  });

  it("returns true on a successful probe response", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await expect(checkScreenerAvailable()).resolves.toBe(true);
  });

  it("returns true when fetch rejects with a network error", async () => {
    // A rejected fetch (DNS failure, connection refused, offline, etc.) means
    // there is no Response object and therefore no status code. The probe
    // treats "no status" as "screener is available" so a transient network
    // blip does not hide the feature from the user; the real request will
    // surface the error if the backend is genuinely unreachable.
    const mockFetch = vi
      .fn()
      .mockRejectedValue(new TypeError("Failed to fetch"));
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await expect(checkScreenerAvailable()).resolves.toBe(true);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });
});

describe("group alpha/tracking error API helpers (request shape and pass-through)", () => {
  // These tests only pin which endpoint each helper calls and that the
  // backend's value is passed through unmodified (#7306). They cannot tell a
  // combined-series figure from an averaged one -- that aggregation semantic
  // is verified on the backend in
  // tests/common/test_group_alpha_combined_series.py.
  beforeEach(() => {
    localStorage.clear();
    setAuthToken(null);
    setApiBase(DEFAULT_API_BASE);
  });

  it("requests group alpha from /performance-group/{slug}/alpha and passes its value through", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ alpha_vs_benchmark: 0.0344 }),
    });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await expect(
      getGroupAlphaVsBenchmark("all", "VWRL.L", 365),
    ).resolves.toEqual({ alpha_vs_benchmark: 0.0344 });

    const [url] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      `${DEFAULT_API_BASE}/performance-group/all/alpha?benchmark=VWRL.L&days=365`,
    );
  });

  it("requests group tracking error from /performance-group/{slug}/tracking-error and passes its value through", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ tracking_error: 0.025 }),
    });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await expect(
      getGroupTrackingError("all", "VWRL.L", 365),
    ).resolves.toEqual({ tracking_error: 0.025 });

    const [url] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      `${DEFAULT_API_BASE}/performance-group/all/tracking-error?benchmark=VWRL.L&days=365`,
    );
  });

  it("shares one request between identical in-flight group metric calls, then refetches once settled (#7629)", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ alpha_vs_benchmark: 0.01 }),
    });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    const [first, second] = await Promise.all([
      getGroupAlphaVsBenchmark("all", "VWRL.L", 365),
      getGroupAlphaVsBenchmark("all", "VWRL.L", 365),
    ]);
    expect(first).toEqual({ alpha_vs_benchmark: 0.01 });
    expect(second).toEqual(first);
    expect(mockFetch).toHaveBeenCalledTimes(1);

    await getGroupAlphaVsBenchmark("all", "VWRL.L", 365);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("gives every sharer the same rejection, then drops the entry so a retry refetches (#7629)", async () => {
    const mockFetch = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ alpha_vs_benchmark: 0.02 }),
      });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    const results = await Promise.allSettled([
      getGroupAlphaVsBenchmark("all", "VWRL.L", 365),
      getGroupAlphaVsBenchmark("all", "VWRL.L", 365),
    ]);
    expect(results.map((r) => r.status)).toEqual(["rejected", "rejected"]);
    expect(mockFetch).toHaveBeenCalledTimes(1);

    await expect(getGroupAlphaVsBenchmark("all", "VWRL.L", 365)).resolves.toEqual({
      alpha_vs_benchmark: 0.02,
    });
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("does not share requests between different group metric URLs (#7629)", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await Promise.all([
      getGroupAlphaVsBenchmark("all", "VWRL.L", 365),
      getGroupAlphaVsBenchmark("all", "VWRL.L", 30),
      getGroupTrackingError("all", "VWRL.L", 365),
    ]);
    expect(mockFetch).toHaveBeenCalledTimes(3);
  });

  it("leaves owner-scoped alpha and tracking error on their own endpoints", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ alpha_vs_benchmark: 0.01 }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ tracking_error: 0.02 }),
      });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await getAlphaVsBenchmark("jane", "VWRL.L", 365);
    await getTrackingError("jane", "VWRL.L", 365);

    const urls = mockFetch.mock.calls.map(([url]) => url as string);
    expect(urls[0]).toBe(
      `${DEFAULT_API_BASE}/performance/jane/alpha?benchmark=VWRL.L&days=365`,
    );
    expect(urls[1]).toBe(
      `${DEFAULT_API_BASE}/performance/jane/tracking-error?benchmark=VWRL.L&days=365`,
    );
  });
});

describe("quote-currency exposure endpoints (#9686)", () => {
  beforeEach(() => {
    localStorage.clear();
    setAuthToken(null);
    setApiBase(DEFAULT_API_BASE);
  });

  it.each([
    [() => getGroupCurrencyContributions("all"), "/portfolio-group/all/currencies"],
    [
      () => getGroupCurrencyContributions("all", { asOf: "2024-01-15" }),
      "/portfolio-group/all/currencies?as_of=2024-01-15",
    ],
    [() => getOwnerCurrencyContributions("jane"), "/portfolio/jane/currencies"],
    [
      () => getOwnerCurrencyContributions("jane", { asOf: "2024-01-15" }),
      "/portfolio/jane/currencies?as_of=2024-01-15",
    ],
  ])("requests %#", async (call, path) => {
    const rows = [{ quote_currency: "USD", market_value_gbp: 10, gain_gbp: 0, cost_gbp: 10 }];
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(rows) });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await expect(call()).resolves.toEqual(rows);

    const [url] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${DEFAULT_API_BASE}${path}`);
  });
});

describe("look-through endpoints (#9974)", () => {
  beforeEach(() => {
    localStorage.clear();
    setAuthToken(null);
    setApiBase(DEFAULT_API_BASE);
  });

  it.each([
    [() => getGroupLookThrough("all"), "/portfolio-group/all/look-through"],
    [() => getGroupLookThrough("all", { asOf: "2024-01-15" }), "/portfolio-group/all/look-through?as_of=2024-01-15"],
    [() => getOwnerLookThrough("jane"), "/portfolio/jane/look-through"],
    [() => getInstrumentAllocation("MINV.L"), "/instrument/allocation?ticker=MINV.L"],
  ])("requests %#", async (call, path) => {
    const body = { total_value_gbp: 0 };
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(body) });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await expect(call()).resolves.toEqual(body);

    const [url] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${DEFAULT_API_BASE}${path}`);
  });

  it("posts a single-fund refresh to the admin route", async () => {
    const body = { updated: true, allocation: {} };
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(body) });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await expect(refreshInstrumentLookThrough("BT-A.L")).resolves.toEqual(body);

    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${DEFAULT_API_BASE}/instrument/admin/L/BT-A/look-through`);
    expect(init.method).toBe("POST");
  });

  it("rejects a refresh for a ticker without an exchange suffix", async () => {
    const mockFetch = vi.fn();
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await expect(refreshInstrumentLookThrough("MINV")).rejects.toThrow("no exchange suffix");
    expect(mockFetch).not.toHaveBeenCalled();
  });
});

describe("cached responses do not survive an identity change", () => {
  beforeEach(() => {
    localStorage.clear();
    setApiBase(DEFAULT_API_BASE);
    setAuthToken(null);
    clearFetchCache();
    clearGroupInstrumentCache();
  });

  afterEach(() => {
    setAuthToken(null);
    clearFetchCache();
    clearGroupInstrumentCache();
  });

  it("clears the fetch cache when a different token is set", () => {
    writeFetchCache("portfolio-group:all:", { total: 1 });
    expect(readFetchCache("portfolio-group:all:")).toBeDefined();

    // Signing in: the local-dev and demo logout paths navigate client-side
    // rather than reloading, so without this the next user on the same tab
    // would be served the previous user's cached portfolio.
    setAuthToken("token-for-user-a");

    expect(readFetchCache("portfolio-group:all:")).toBeUndefined();
  });

  it("clears the fetch cache on logout", () => {
    setAuthToken("token-for-user-a");
    writeFetchCache("portfolio-group:all:", { total: 1 });

    setAuthToken(null);

    expect(readFetchCache("portfolio-group:all:")).toBeUndefined();
  });

  it("keeps the cache when the same token is re-set", () => {
    setAuthToken("token-for-user-a");
    writeFetchCache("portfolio-group:all:", { total: 1 });

    // A token refresh for the same user must not throw the cache away.
    setAuthToken("token-for-user-a");

    expect(readFetchCache("portfolio-group:all:")).toBeDefined();
  });
});

describe("setAuthToken auth-change events (issue #8618)", () => {
  afterEach(() => {
    setAuthToken(null);
  });

  it("emits once per actual token change, with the previous token", () => {
    setAuthToken(null);
    const listener = vi.fn();
    const unsubscribe = onAuthChange(listener);

    setAuthToken("token-for-user-a");
    // Re-setting the same token is not a change.
    setAuthToken("token-for-user-a");
    setAuthToken(null);
    unsubscribe();

    expect(listener.mock.calls).toEqual([
      [{ previousToken: null, nextToken: "token-for-user-a" }],
      [{ previousToken: "token-for-user-a", nextToken: null }],
    ]);
  });
});

describe("chat conversation is scoped to the login session", () => {
  const message = { role: "user" as const, content: "What is my ISA worth?" };

  beforeEach(() => {
    setAuthToken(null);
    startNewChat();
  });

  afterEach(() => {
    setAuthToken(null);
    startNewChat();
  });

  it("clears the conversation on logout", () => {
    setAuthToken("token-for-user-a");
    appendChatMessage(message);

    setAuthToken(null);

    expect(getChatMessages()).toEqual([]);
    // Nothing of the conversation, in any version, is left in storage (#8842).
    expect(JSON.parse(sessionStorage.getItem("allotmint.chat.tree.v1") ?? "null")).toMatchObject({
      nodes: [],
      active: {},
    });
    expect(sessionStorage.getItem("allotmint.chat.messages")).toBeNull();
  });

  it("keeps the conversation when the stored token is re-applied on reload", () => {
    appendChatMessage(message);

    // main.tsx restores the stored token from a null start on every load.
    setAuthToken("token-for-user-a");

    expect(getChatMessages()).toEqual([message]);
  });

  it("keeps the conversation across a token refresh", () => {
    setAuthToken("token-for-user-a");
    appendChatMessage(message);

    // The Cognito refresh swaps in a new token for the same user.
    setAuthToken("refreshed-token-for-user-a");

    expect(getChatMessages()).toEqual([message]);
  });

  it("on a direct switch to another user's token, keeps the chat only until the sync reloads (#8770)", () => {
    setAuthToken("token-for-user-a");
    appendChatMessage(message);
    const epoch = getChatIdentityEpoch();

    // No intervening null: indistinguishable here from a refresh, so nothing
    // is cleared yet. The epoch bump makes the chat sync reload before it
    // shows or saves anything else, and that reload replaces a conversation
    // cached for a different owner (utils/chatSync.test.ts).
    setAuthToken("token-for-user-b");

    expect(getChatMessages()).toEqual([message]);
    expect(getChatIdentityEpoch()).toBeGreaterThan(epoch);
  });
});

describe("saved chat conversation API (#8870)", () => {
  const tree = {
    nodes: [{ id: "1", parentId: null, role: "user" as const, content: "hi" }],
    active: { root: "1" },
    nextId: 2,
  };

  const respond = (status: number, body: unknown) =>
    vi.fn().mockResolvedValue({
      ok: status < 400,
      status,
      statusText: "",
      headers: new Headers(),
      json: () => Promise.resolve(body),
      text: () => Promise.resolve(""),
    });

  it("GETs the saved conversation", async () => {
    const saved = { owner: "abc", revision: 3, conversation: tree };
    const mockFetch = respond(200, saved);
    global.fetch = mockFetch;

    await expect(getChatConversation()).resolves.toEqual(saved);
    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${DEFAULT_API_BASE}/chat/conversation`);
    expect(init.method).toBeUndefined();
  });

  it("PUTs the tree with the revision it was based on", async () => {
    const mockFetch = respond(200, { revision: 4 });
    global.fetch = mockFetch;

    await expect(putChatConversation(tree, 3)).resolves.toEqual({ revision: 4 });
    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${DEFAULT_API_BASE}/chat/conversation`);
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({ revision: 3, conversation: tree });
  });

  it("rejects a stale PUT with the saved document on the error", async () => {
    const current = { revision: 5, conversation: tree };
    global.fetch = respond(409, { detail: "changed", code: "chat_conversation_conflict", current });

    await expect(putChatConversation(tree, 3)).rejects.toMatchObject({
      status: 409,
      code: "chat_conversation_conflict",
      body: { current },
    });
  });

  it("archives with POST and deletes the history with DELETE", async () => {
    const mockFetch = respond(200, { revision: 2, archived: true });
    global.fetch = mockFetch;
    await expect(archiveChatConversation()).resolves.toEqual({ revision: 2, archived: true });
    expect(mockFetch.mock.calls[0][0]).toBe(`${DEFAULT_API_BASE}/chat/conversation/archive`);
    expect((mockFetch.mock.calls[0][1] as RequestInit).method).toBe("POST");

    const deleteFetch = respond(204, null);
    global.fetch = deleteFetch;
    await expect(deleteChatHistory()).resolves.toBeUndefined();
    expect(deleteFetch.mock.calls[0][0]).toBe(`${DEFAULT_API_BASE}/chat/conversation`);
    expect((deleteFetch.mock.calls[0][1] as RequestInit).method).toBe("DELETE");
  });
});

describe("saved chat bookkeeping follows the signed-in identity (#8870)", () => {
  afterEach(() => {
    setAuthToken(null);
  });

  it("forgets whose saved copy this tab holds on logout", () => {
    setAuthToken("token-for-user-a");
    setChatSyncState({ owner: "user-a", revision: 7, dirty: true, archivePending: true });

    setAuthToken(null);

    expect(getChatSyncState()).toEqual({ owner: null, revision: 0, dirty: false, archivePending: false });
    expect(JSON.parse(sessionStorage.getItem("allotmint.chat.sync.v1") ?? "null")).toEqual(
      getChatSyncState(),
    );
  });

  it("asks for a reload whenever a different token is applied", () => {
    setAuthToken("token-for-user-a");
    const epoch = getChatIdentityEpoch();

    setAuthToken("token-for-user-a");
    expect(getChatIdentityEpoch()).toBe(epoch);

    setAuthToken("token-for-user-b");
    expect(getChatIdentityEpoch()).toBeGreaterThan(epoch);
  });
});
