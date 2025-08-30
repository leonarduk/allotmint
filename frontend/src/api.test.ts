import { describe, it, expect, vi, beforeEach } from "vitest";
import { fetchJson, setAuthToken } from "./api";

describe("auth token handling", () => {
  beforeEach(() => {
    setAuthToken(null);
  });

  it("adds Authorization header when token set", async () => {
    setAuthToken("token123");
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    // @ts-ignore
    global.fetch = mockFetch;
    await fetchJson("/foo");
    expect(mockFetch).toHaveBeenCalled();
    const args = mockFetch.mock.calls[0];
    const headers = args[1].headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer token123");
  });
});
