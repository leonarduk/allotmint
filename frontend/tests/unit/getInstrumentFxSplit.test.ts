import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  DEFAULT_API_BASE,
  getInstrumentFxSplit,
  setApiBase,
  setAuthToken,
} from '@/api';

describe('getInstrumentFxSplit', () => {
  beforeEach(() => {
    localStorage.clear();
    setAuthToken(null);
    setApiBase(DEFAULT_API_BASE);
  });

  it('requests the cache-only split for the ticker and range', async () => {
    const split = { ticker: 'AAPL.N', applicable: true, gbp_return: 0.045 };
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve(split) });
    global.fetch = mockFetch;

    await expect(getInstrumentFxSplit('AAPL.N', 30)).resolves.toEqual(split);

    const [url] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      `${DEFAULT_API_BASE}/instrument/fx-split?ticker=AAPL.N&days=30`
    );
  });

  it('encodes the ticker and defaults to a year', async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    global.fetch = mockFetch;

    await getInstrumentFxSplit('BRK B.N');

    const [url] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      `${DEFAULT_API_BASE}/instrument/fx-split?ticker=BRK%20B.N&days=365`
    );
  });
});
