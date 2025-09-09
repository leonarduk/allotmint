import { describe, it, expect, vi, beforeEach } from "vitest";
import { API_BASE, fetchJson, setAuthToken, login, subscribeNudges } from "./api";

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
