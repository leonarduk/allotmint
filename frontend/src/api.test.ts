import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  API_BASE,
  fetchJson,
  setAuthToken,
  login,
  subscribeNudges,
  getEvents,
  runScenario,
  getPensionForecast,
} from "./api";

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
});
