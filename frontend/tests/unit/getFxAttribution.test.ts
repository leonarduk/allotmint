import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  DEFAULT_API_BASE,
  getFxAttribution,
  setApiBase,
  setAuthToken,
} from '@/api';

describe('getFxAttribution', () => {
  beforeEach(() => {
    localStorage.clear();
    setAuthToken(null);
    setApiBase(DEFAULT_API_BASE);
  });

  it("requests the owner's attribution for the range and as-of date", async () => {
    const body = { owner: 'alice', fx_attribution: null };
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve(body) });
    global.fetch = mockFetch;

    await expect(
      getFxAttribution('alice', 30, { asOf: '2026-01-30' })
    ).resolves.toEqual(body);

    const [url] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      `${DEFAULT_API_BASE}/performance/alice/fx-attribution?days=30&as_of=2026-01-30`
    );
  });

  it('defaults to a year and encodes the owner', async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    global.fetch = mockFetch;

    await getFxAttribution('a b');

    const [url] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      `${DEFAULT_API_BASE}/performance/a%20b/fx-attribution?days=365`
    );
  });
});
