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
  UNAUTHORIZED_EVENT,
  reconcileHoldingsCsv,
  importHoldingsCsv,
  runCustomQuery,
  getCachedGroupInstruments,
  clearGroupInstrumentCache,
  checkScreenerAvailable,
} from "@/api";
import {
  clearFetchCache,
  readFetchCache,
  writeFetchCache,
} from "@/utils/fetchCache";

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
      "http://localhost:8000",
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
      "http://localhost:8000",
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
      "http://localhost:8000",
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
  // clicking "Retry" in ScreenerQuery) replays the SAME rejection forever,
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
      "http://localhost:8000",
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
      "http://localhost:8000",
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
      "http://localhost:8000",
      null,
      mockFetch as unknown as typeof fetch,
      { fetchTimeoutMs: 5000 },
    );

    const pending = testFetchJson("/owners", { signal: controller.signal });
    const assertion = expect(pending).rejects.toMatchObject({ name: "AbortError" });

    controller.abort();
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
  it("POSTs the query body -- the backend only exposes POST /custom-query/run", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ results: [{ ticker: "AAA.L" }] }),
    });
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    const rows = await runCustomQuery({
      start: "2024-01-01",
      end: "2024-02-01",
      owners: ["alex"],
      tickers: ["AAA.L"],
      metrics: ["meta"],
    });

    // The GET form this replaced 404'd: no such route existed.
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe(`${API_BASE}/custom-query/run`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      start: "2024-01-01",
      end: "2024-02-01",
      owners: ["alex"],
      tickers: ["AAA.L"],
      metrics: ["meta"],
      format: "json",
    });
    // The endpoint wraps rows in {results}; callers expect the bare array.
    expect(rows).toEqual([{ ticker: "AAA.L" }]);
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
    // The resulting fullUrl is "http://localhost:8000//evil.com/path" — origin is still
    // http://localhost:8000, so the SSRF guard passes.  This test pins that behaviour.
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
      "http://localhost:8000/api/v1",
      null,
      mockFetch as unknown as typeof fetch,
    );
    await testFetchJson("/holdings?owner=alice#section");
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/holdings?owner=alice#section",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });

  it("still blocks a same-origin path outside the configured prefix when reconstructing", async () => {
    const mockFetch = vi.fn();
    const { fetchJson: testFetchJson } = createClient(
      "http://localhost:8000/api/v1",
      null,
      mockFetch as unknown as typeof fetch,
    );
    await expect(
      testFetchJson("http://localhost:8000/other-app/steal?x=1"),
    ).rejects.toThrow("does not start with configured API base");
    expect(mockFetch).not.toHaveBeenCalled();
  });
});

describe("path-prefix guard (issue #3170)", () => {
  it("blocks a same-origin URL that does not match the configured API path prefix", async () => {
    const { fetchJson: testFetchJson } = createClient("http://localhost:8000/api/v1");
    await expect(
      testFetchJson("http://localhost:8000/other-app/steal"),
    ).rejects.toThrow("does not start with configured API base");
  });

  it("blocks a same-origin URL that shares the prefix string but is not within the prefix path", async () => {
    const { fetchJson: testFetchJson } = createClient("http://localhost:8000/api/v1");
    await expect(
      testFetchJson("http://localhost:8000/api/v1other"),
    ).rejects.toThrow("does not start with configured API base");
  });

  it("allows a same-origin absolute URL that starts with the configured API path prefix", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    const { fetchJson: testFetchJson } = createClient(
      "http://localhost:8000/api/v1",
      null,
      mockFetch as unknown as typeof fetch,
    );
    await testFetchJson("http://localhost:8000/api/v1/users");
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/users",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });

  it("allows a relative path that resolves under the configured API path prefix", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    const { fetchJson: testFetchJson } = createClient(
      "http://localhost:8000/api/v1",
      null,
      mockFetch as unknown as typeof fetch,
    );
    await testFetchJson("/users");
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/users",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });

  it("allows a URL that exactly equals the configured API base", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    const { fetchJson: testFetchJson } = createClient(
      "http://localhost:8000/api/v1",
      null,
      mockFetch as unknown as typeof fetch,
    );
    await testFetchJson("http://localhost:8000/api/v1");
    expect(mockFetch).toHaveBeenCalled();
  });

  it("allows a URL that equals the configured API base with query params appended", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    const { fetchJson: testFetchJson } = createClient(
      "http://localhost:8000/api/v1",
      null,
      mockFetch as unknown as typeof fetch,
    );
    await testFetchJson("http://localhost:8000/api/v1?filter=x");
    expect(mockFetch).toHaveBeenCalled();
  });

  it("normalises a trailing slash in the configured API base and still blocks wrong paths", async () => {
    const { fetchJson: testFetchJson } = createClient("http://localhost:8000/api/v1/");
    await expect(
      testFetchJson("http://localhost:8000/other-app/steal"),
    ).rejects.toThrow("does not start with configured API base");
  });

  it("normalises a trailing slash in the configured API base and still allows correct paths", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    const { fetchJson: testFetchJson } = createClient(
      "http://localhost:8000/api/v1/",
      null,
      mockFetch as unknown as typeof fetch,
    );
    await testFetchJson("http://localhost:8000/api/v1/users");
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
  it("fetches signals and settings and combines them", async () => {
    const signals = [{ ticker: "AAA", action: "BUY", reason: "r" }];
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
            url.endsWith("/trading-agent/settings") ? settings : signals,
          ),
      }),
    );
    // @ts-expect-error: replacing global fetch with mock
    global.fetch = mockFetch;

    await expect(getTradingPageData()).resolves.toEqual({ signals, settings });

    const calledUrls = mockFetch.mock.calls.map(([url]) => url as string);
    expect(calledUrls).toContain(`${API_BASE}/trading-agent/signals`);
    expect(calledUrls).toContain(`${API_BASE}/trading-agent/settings`);
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
