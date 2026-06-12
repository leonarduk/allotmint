import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  DEFAULT_API_BASE,
  API_BASE,
  createClient,
  fetchJson,
  setAuthToken,
  setApiBase,
  login,
  subscribeNudges,
  getEvents,
  runScenario,
  getPortfolio,
  getPensionForecast,
  getConfig,
} from "@/api";

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
