import { renderHook, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterAll, afterEach } from 'vitest';
// Mock the API module so we can reliably intercept calls across ESM boundaries
vi.mock('@/api', () => ({
  fetchInstrumentDetailWithRetry: vi.fn(),
  fetchInstrumentBatchWithRetry: vi.fn(),
}));
import * as api from '@/api';
import {
  useInstrumentHistory,
  preloadInstrumentHistory,
  getCachedInstrumentHistory,
  __clearInstrumentHistoryCache,
} from '@/hooks/useInstrumentHistory';

const mockGetInstrumentDetail = api
  .fetchInstrumentDetailWithRetry as unknown as ReturnType<typeof vi.fn>;
const mockGetInstrumentBatch = api
  .fetchInstrumentBatchWithRetry as unknown as ReturnType<typeof vi.fn>;

afterAll(() => {
  mockGetInstrumentDetail.mockRestore();
  mockGetInstrumentBatch.mockRestore();
});

describe('useInstrumentHistory', () => {
  beforeEach(() => {
    mockGetInstrumentDetail.mockReset();
    mockGetInstrumentBatch.mockReset();
    __clearInstrumentHistoryCache();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it.each([
    { ticker: '', days: 7 },
    { ticker: 'ABC', days: 0 },
    { ticker: 'ABC', days: -1 },
  ])('does not fetch without a valid ticker and day range', ({ ticker, days }) => {
    const { result } = renderHook(() => useInstrumentHistory(ticker, days));

    expect(mockGetInstrumentDetail).not.toHaveBeenCalled();
    expect(result.current).toEqual({ data: null, loading: false, error: null });
  });

  it('retries on HTTP 429 responses and succeeds', async () => {
    vi.useFakeTimers();
    mockGetInstrumentDetail
      .mockRejectedValueOnce(new Error('HTTP 429 – Too Many Requests'))
      .mockResolvedValueOnce({
        mini: { 7: [], 30: [], 180: [] },
        positions: [],
      });

    const { result } = renderHook(() => useInstrumentHistory('ABC', 7));

    await act(async () => {
      await vi.runAllTimersAsync();
      await vi.advanceTimersByTimeAsync(2000);
      await vi.runAllTimersAsync();
    });

    expect(mockGetInstrumentDetail).toHaveBeenCalledTimes(2);
    expect(mockGetInstrumentDetail).toHaveBeenNthCalledWith(1, 'ABC', 7);
    expect(mockGetInstrumentDetail).toHaveBeenNthCalledWith(2, 'ABC', 7);
    expect(result.current.error).toBeNull();
    expect(result.current.data).not.toBeNull();
  });

  it('uses Retry-After header for backoff', async () => {
    vi.useFakeTimers();
    const randSpy = vi.spyOn(Math, 'random').mockReturnValue(0);

    const err = new Error('HTTP 429 – Too Many Requests') as any;
    err.response = { headers: new Headers({ 'Retry-After': '2' }) };

    mockGetInstrumentDetail.mockRejectedValueOnce(err).mockResolvedValueOnce({
      mini: { 7: [], 30: [], 180: [] },
      positions: [],
    });

    const { result } = renderHook(() => useInstrumentHistory('ABC', 7));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(mockGetInstrumentDetail).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
      await vi.runAllTimersAsync();
    });
    expect(mockGetInstrumentDetail).toHaveBeenCalledTimes(2);
    expect(mockGetInstrumentDetail).toHaveBeenNthCalledWith(1, 'ABC', 7);
    expect(mockGetInstrumentDetail).toHaveBeenNthCalledWith(2, 'ABC', 7);
    expect(result.current.data).not.toBeNull();

    randSpy.mockRestore();
  });

  it('caches detail per ticker and day range', async () => {
    mockGetInstrumentDetail.mockResolvedValue({
      mini: { 7: [], 30: [], 180: [], 365: [] },
      positions: [],
    });

    const { result, rerender } = renderHook(
      ({ days }) => useInstrumentHistory('ABC', days),
      { initialProps: { days: 7 } }
    );

    await waitFor(() => expect(result.current.data).not.toBeNull());
    expect(mockGetInstrumentDetail).toHaveBeenCalledTimes(1);
    expect(mockGetInstrumentDetail).toHaveBeenLastCalledWith('ABC', 7);

    rerender({ days: 7 });
    await waitFor(() => expect(result.current.data).not.toBeNull());
    expect(mockGetInstrumentDetail).toHaveBeenCalledTimes(1);

    rerender({ days: 30 });
    await waitFor(() => expect(result.current.data).not.toBeNull());
    expect(mockGetInstrumentDetail).toHaveBeenCalledTimes(2);
    expect(mockGetInstrumentDetail).toHaveBeenLastCalledWith('ABC', 30);
  });

  it('dedupes hook consumers mounted for the same ticker and days', async () => {
    let release!: (value: unknown) => void;
    const gate = new Promise((resolve) => {
      release = resolve;
    });
    mockGetInstrumentDetail.mockReturnValueOnce(
      gate.then(() => ({
        mini: { 7: [], 30: [], 180: [] },
        positions: [],
      })),
    );

    const first = renderHook(() => useInstrumentHistory('ABC', 7));
    const second = renderHook(() => useInstrumentHistory('ABC', 7));

    await act(async () => {
      release({
        mini: { 7: [], 30: [], 180: [] },
        positions: [],
      });
    });

    await waitFor(() => {
      expect(first.result.current.data).not.toBeNull();
      expect(second.result.current.data).not.toBeNull();
    });
    expect(mockGetInstrumentDetail).toHaveBeenCalledTimes(1);
  });

  describe('acceptMiniOnly mode', () => {
    it('fetches via the batch endpoint instead of the single-ticket endpoint', async () => {
      mockGetInstrumentBatch.mockResolvedValue({
        instruments: { ABC: { prices: [{ date: '2024-01-01', close: 10 }] } },
        empty: [],
        unknown: [],
      });

      const { result } = renderHook(() =>
        useInstrumentHistory('ABC', 7, { acceptMiniOnly: true }),
      );

      await waitFor(() => expect(result.current.data).not.toBeNull());
      expect(mockGetInstrumentDetail).not.toHaveBeenCalled();
      expect(mockGetInstrumentBatch).toHaveBeenCalledTimes(1);
      expect(mockGetInstrumentBatch).toHaveBeenCalledWith(['ABC'], 7, true);
      expect(result.current.data?.prices).toEqual([{ date: '2024-01-01', close: 10 }]);
    });

    it('coalesces concurrent mini-only requests for the same days into one batch call', async () => {
      mockGetInstrumentBatch.mockResolvedValue({
        instruments: {
          ABC: { prices: [{ date: '2024-01-01', close: 10 }] },
          DEF: { prices: [{ date: '2024-01-01', close: 20 }] },
        },
        empty: [],
        unknown: [],
      });

      const first = renderHook(() => useInstrumentHistory('ABC', 30, { acceptMiniOnly: true }));
      const second = renderHook(() => useInstrumentHistory('DEF', 30, { acceptMiniOnly: true }));

      await waitFor(() => {
        expect(first.result.current.data).not.toBeNull();
        expect(second.result.current.data).not.toBeNull();
      });

      expect(mockGetInstrumentBatch).toHaveBeenCalledTimes(1);
      expect(mockGetInstrumentBatch).toHaveBeenCalledWith(
        expect.arrayContaining(['ABC', 'DEF']),
        30,
        true,
      );
    });

    it('does not fetch when a full-detail cache entry already covers the ticker', async () => {
      mockGetInstrumentDetail.mockResolvedValue({
        prices: [{ date: '2024-01-01', close: 10 }],
        mini: { 30: [{ date: '2024-01-01', close: 10 }] },
        positions: [],
      });
      // Warm the full-detail cache first, as InstrumentResearch would.
      const full = renderHook(() => useInstrumentHistory('ABC', 30));
      await waitFor(() => expect(full.result.current.data).not.toBeNull());

      const mini = renderHook(() => useInstrumentHistory('ABC', 30, { acceptMiniOnly: true }));

      expect(mini.result.current.loading).toBe(false);
      expect(mini.result.current.data?.mini?.[30]).toEqual([{ date: '2024-01-01', close: 10 }]);
      expect(mockGetInstrumentBatch).not.toHaveBeenCalled();
    });

    it('a batch-derived cache entry does not satisfy a later full-detail request', async () => {
      mockGetInstrumentBatch.mockResolvedValue({
        instruments: { ABC: { prices: [{ date: '2024-01-01', close: 10 }] } },
        empty: [],
        unknown: [],
      });
      mockGetInstrumentDetail.mockResolvedValue({
        prices: [{ date: '2024-01-01', close: 10 }],
        positions: [{ owner: 'alice', account: 'isa', units: 1 }],
      });

      // A sparkline preloads/reads mini-only data first...
      const mini = renderHook(() => useInstrumentHistory('ABC', 30, { acceptMiniOnly: true }));
      await waitFor(() => expect(mini.result.current.data).not.toBeNull());
      expect(mockGetInstrumentDetail).not.toHaveBeenCalled();

      // ...but a page needing full detail (positions) at the same (ticker, days)
      // must still fetch it, not silently reuse the partial batch entry.
      const full = renderHook(() => useInstrumentHistory('ABC', 30));
      await waitFor(() => expect(full.result.current.data).not.toBeNull());
      expect(mockGetInstrumentDetail).toHaveBeenCalledTimes(1);
      expect(full.result.current.data?.positions).toEqual([
        { owner: 'alice', account: 'isa', units: 1 },
      ]);
    });
  });
});

describe('preloadInstrumentHistory', () => {
  beforeEach(() => {
    mockGetInstrumentDetail.mockReset();
    mockGetInstrumentBatch.mockReset();
    __clearInstrumentHistoryCache();
  });

  it('fetches via one batch call for all requested tickers', async () => {
    mockGetInstrumentBatch.mockResolvedValue({
      instruments: {
        ABC: { prices: [{ date: '2024-01-01', close: 1 }] },
        DEF: { prices: [{ date: '2024-01-01', close: 2 }] },
      },
      empty: [],
      unknown: [],
    });

    await preloadInstrumentHistory(['ABC', 'DEF'], 30);

    expect(mockGetInstrumentDetail).not.toHaveBeenCalled();
    expect(mockGetInstrumentBatch).toHaveBeenCalledTimes(1);
    expect(mockGetInstrumentBatch).toHaveBeenCalledWith(
      expect.arrayContaining(['ABC', 'DEF']),
      30,
      true,
    );
  });

  it('shares one in-flight batch call across concurrent preload callers', async () => {
    mockGetInstrumentBatch.mockResolvedValue({
      instruments: {
        ABC: { prices: [{ date: '2024-01-01', close: 1 }] },
        DEF: { prices: [{ date: '2024-01-01', close: 2 }] },
      },
      empty: [],
      unknown: [],
    });

    await Promise.all([
      preloadInstrumentHistory(['ABC', 'DEF'], 30),
      preloadInstrumentHistory(['ABC', 'DEF'], 30),
    ]);

    expect(mockGetInstrumentBatch).toHaveBeenCalledTimes(1);
  });

  it('does not cache a batch failure so a later preload retries', async () => {
    mockGetInstrumentBatch
      .mockRejectedValueOnce(new Error('HTTP 500'))
      .mockResolvedValueOnce({
        instruments: { ABC: { prices: [{ date: '2024-01-01', close: 1 }] } },
        empty: [],
        unknown: [],
      });

    await preloadInstrumentHistory(['ABC'], 30);
    await preloadInstrumentHistory(['ABC'], 30);

    expect(mockGetInstrumentBatch).toHaveBeenCalledTimes(2);
  });

  it('returns tickers that resolved to an empty history, ignoring unknown ones', async () => {
    mockGetInstrumentBatch.mockResolvedValue({
      instruments: { 'B.L': { prices: [{ date: '2024-01-01', close: 1 }] } },
      empty: ['A.L', 'C.L'],
      unknown: ['D.L'],
    });

    const missing = await preloadInstrumentHistory(['A.L', 'B.L', 'C.L', 'D.L'], 30);

    expect(missing).toEqual(['A.L', 'C.L']);
  });

  it('caches empty responses so later preloads do not refetch', async () => {
    mockGetInstrumentBatch.mockResolvedValue({
      instruments: {},
      empty: ['A.L'],
      unknown: [],
    });

    await preloadInstrumentHistory(['A.L'], 30);
    const missing = await preloadInstrumentHistory(['A.L'], 30);

    expect(mockGetInstrumentBatch).toHaveBeenCalledTimes(1);
    expect(missing).toEqual(['A.L']);
    expect(getCachedInstrumentHistory('A.L', 30)?.prices).toEqual([]);
  });

  it('ignores unknown tickers in the notice set', async () => {
    mockGetInstrumentBatch.mockResolvedValue({
      instruments: {},
      empty: [],
      unknown: ['A.L'],
    });

    const missing = await preloadInstrumentHistory(['A.L'], 30);

    expect(missing).toEqual([]);
  });

  it('deduplicates tickers passed multiple times before batching', async () => {
    mockGetInstrumentBatch.mockResolvedValue({
      instruments: {},
      empty: ['A.L', 'B.L'],
      unknown: [],
    });

    const missing = await preloadInstrumentHistory(['A.L', 'A.L', 'B.L'], 30);

    expect(mockGetInstrumentBatch).toHaveBeenCalledTimes(1);
    expect(mockGetInstrumentBatch).toHaveBeenCalledWith(['A.L', 'B.L'], 30, true);
    expect(missing).toEqual(['A.L', 'B.L']);
  });

  it('reuses an existing full-detail cache entry instead of batching', async () => {
    mockGetInstrumentDetail.mockResolvedValue({
      prices: [],
      positions: [],
    });
    const full = renderHook(() => useInstrumentHistory('A.L', 30));
    await waitFor(() => expect(full.result.current.data).not.toBeNull());

    const missing = await preloadInstrumentHistory(['A.L'], 30);

    expect(mockGetInstrumentBatch).not.toHaveBeenCalled();
    expect(missing).toEqual(['A.L']);
  });
});
