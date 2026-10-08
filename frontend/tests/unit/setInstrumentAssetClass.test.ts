import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  DEFAULT_API_BASE,
  setApiBase,
  setAuthToken,
  setInstrumentAssetClass,
} from '@/api';

const ok = () => ({ ok: true, status: 200, json: () => Promise.resolve({}) });

describe('setInstrumentAssetClass (#9495)', () => {
  beforeEach(() => {
    localStorage.clear();
    setAuthToken(null);
    setApiBase(DEFAULT_API_BASE);
  });

  it('merges only the asset class into existing metadata', async () => {
    const mockFetch = vi.fn().mockResolvedValue(ok());
    global.fetch = mockFetch;

    await setInstrumentAssetClass('QQQ', 'N', 'equity', 'Invesco QQQ');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${DEFAULT_API_BASE}/instrument/admin/N/QQQ`);
    expect(init.method).toBe('PUT');
    // The body is intentionally partial: the backend PUT is a merge, so
    // sending only `asset_class` preserves `name`, `sector`, etc. Widening
    // this body would introduce a read-modify-write race (see api.ts).
    expect(JSON.parse(String(init.body))).toEqual({ asset_class: 'equity' });
  });

  it('creates the metadata when the instrument has none', async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        json: () => Promise.resolve({ detail: 'Instrument not found' }),
      })
      .mockResolvedValueOnce(ok());
    global.fetch = mockFetch;

    await setInstrumentAssetClass('QQQ', 'N', 'equity', null);

    expect(mockFetch).toHaveBeenCalledTimes(2);
    const [url, init] = mockFetch.mock.calls[1] as [string, RequestInit];
    expect(url).toBe(`${DEFAULT_API_BASE}/instrument/admin/N/QQQ`);
    expect(init.method).toBe('POST');
    // Matches the backend `create_instrument` contract: `ticker` must equal
    // `${ticker}.${exchange}` and `exchange` must equal the path segment,
    // otherwise the handler answers 400 "Ticker mismatch".
    expect(JSON.parse(String(init.body))).toEqual({
      ticker: 'QQQ.N',
      exchange: 'N',
      name: 'QQQ',
      asset_class: 'equity',
    });
  });

  it('surfaces other failures without creating metadata', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      statusText: 'Bad Request',
      json: () => Promise.resolve({ detail: 'Invalid ticker' }),
    });
    global.fetch = mockFetch;

    await expect(setInstrumentAssetClass('QQQ', 'N', 'equity')).rejects.toThrow(
      'Invalid ticker'
    );
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });
});
