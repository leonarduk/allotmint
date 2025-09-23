import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  API_BASE,
  fetchJson,
  setAuthToken,
  login,
  subscribeNudges,
  getEvents,
  runScenario,
  getPortfolio,
  getPensionForecast,
} from "@/api";

describe("auth token handling", () => {
  beforeEach(() => {
    localStorage.clear();
    setAuthToken(null);
  });

  it("stores token in localStorage and adds header", async () => {
    setAuthToken("token123");
    expect(localStorage.getItem("authToken")).toBe("token123");
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    // @ts-ignore
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
  });

  it("succeeds for allowed tokens", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ access_token: "abc" }),
      });
    // @ts-ignore
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
    // @ts-ignore
    global.fetch = mockFetch;
    await expect(login("bad-id-token")).rejects.toThrow("Login failed");
  });
});

describe("nudge subscriptions", () => {
  it("clamps frequency within bounds", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    // @ts-ignore
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
    // @ts-ignore
    global.fetch = mockFetch;
    const data = await getPortfolio("alice");
    const holding = data.accounts[0].holdings[0];
    expect(holding.last_price_time).toBe("2024-01-01T10:00:00Z");
    expect(holding.is_stale).toBe(true);
  });
});

describe("scenario APIs", () => {
  it("fetches events", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
    // @ts-ignore
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
    // @ts-ignore
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
    // @ts-ignore
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
    // @ts-ignore
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
