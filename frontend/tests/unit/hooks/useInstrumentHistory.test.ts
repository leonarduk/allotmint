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

    it('derives mini from prices when a full-detail cache entry has none (Phase 3b, ADR #6911 §8)', async () => {
      // /instrument/ now omits `mini` by default (include_mini opt-in), so a
      // full-detail entry warmed by InstrumentResearch.tsx (no acceptMiniOnly)
      // has no `.mini` for a later same-(ticker,days) sparkline read to find.
      const prices = Array.from({ length: 40 }, (_, i) => ({ date: `d${i}`, close: i }));
      mockGetInstrumentDetail.mockResolvedValue({ prices, positions: [] });

      const full = renderHook(() => useInstrumentHistory('ABC', 30));
      await waitFor(() => expect(full.result.current.data).not.toBeNull());
      expect(full.result.current.data?.mini).toBeUndefined();

      const mini = renderHook(() => useInstrumentHistory('ABC', 30, { acceptMiniOnly: true }));

      expect(mini.result.current.loading).toBe(false);
      expect(mockGetInstrumentBatch).not.toHaveBeenCalled();
      // Row-count slice of the tail, matching backend/common/instrument_api.py's
      // `out[-30:]` contract -- not a calendar-day cutoff (ADR §4.5 is a
      // different, larger derivation for a different cache shape).
      expect(mini.result.current.data?.mini?.[30]).toEqual(prices.slice(-30));
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

    it('resolves to null (not an error, not a crash) for an unknown ticker, and stays retryable', async () => {
      mockGetInstrumentBatch
        .mockResolvedValueOnce({ instruments: {}, empty: [], unknown: ['ABC'] })
        .mockResolvedValueOnce({
          instruments: { ABC: { prices: [{ date: '2024-01-01', close: 10 }] } },
          empty: [],
          unknown: [],
        });

      const first = renderHook(() => useInstrumentHistory('ABC', 30, { acceptMiniOnly: true }));
      await waitFor(() => expect(first.result.current.loading).toBe(false));
      expect(first.result.current.data).toBeNull();
      expect(first.result.current.error).toBeNull();

      // Nothing was cached for the unknown ticker, so a fresh mount retries
      // rather than reusing a pinned miss.
      const second = renderHook(() => useInstrumentHistory('ABC', 30, { acceptMiniOnly: true }));
      await waitFor(() => expect(second.result.current.data).not.toBeNull());
      expect(mockGetInstrumentBatch).toHaveBeenCalledTimes(2);
    });

    it('resolves to null, not a thrown error, when the batch request itself fails', async () => {
      // acceptMiniOnly mode doesn't surface a distinct `error` for a failed
      // batch request today -- Sparkline/InstrumentTile (the only current
      // consumers) render the same empty state for data:null as they do for
      // a truthy `error`, so this documents current behavior rather than
      // asserting a stronger contract nothing yet relies on.
      mockGetInstrumentBatch.mockRejectedValueOnce(new Error('HTTP 500'));

      const { result } = renderHook(() =>
        useInstrumentHistory('ABC', 30, { acceptMiniOnly: true }),
      );

      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(result.current.data).toBeNull();
      expect(result.current.error).toBeNull();
    });
  });
});

describe('getCachedInstrumentHistory mini derivation (Phase 3b, ADR #6911 §8)', () => {
  beforeEach(() => {
    mockGetInstrumentDetail.mockReset();
    mockGetInstrumentBatch.mockReset();
    __clearInstrumentHistoryCache();
  });

  it('derives the requested days slice from prices when a cached full-detail entry has no mini', async () => {
    const prices = Array.from({ length: 10 }, (_, i) => ({ date: `d${i}`, close: i }));
    mockGetInstrumentDetail.mockResolvedValue({ prices, positions: [] });

    const full = renderHook(() => useInstrumentHistory('ABC', 7));
    await waitFor(() => expect(full.result.current.data).not.toBeNull());

    // Sparkline.tsx reads this directly during render, not just via the hook.
    const cached = getCachedInstrumentHistory('ABC', 7);
    expect(cached?.mini?.[7]).toEqual(prices.slice(-7));
  });

  it('leaves a server-supplied mini for the requested days untouched', async () => {
    const serverMini = [{ date: 'd9', close: 99 }];
    mockGetInstrumentDetail.mockResolvedValue({
      prices: [{ date: 'd9', close: 9 }],
      mini: { 7: serverMini },
      positions: [],
    });

    const full = renderHook(() => useInstrumentHistory('ABC', 7));
    await waitFor(() => expect(full.result.current.data).not.toBeNull());

    expect(getCachedInstrumentHistory('ABC', 7)?.mini?.[7]).toEqual(serverMini);
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

  it('resolves every requested spelling of a ticker when the backend case-dedupes the response (#7008 review)', async () => {
    // The same instrument can appear with different casing across accounts
    // (e.g. "ABC.L" and "abc.l"); backend/common/instrument_api.py's
    // dedupe_tickers collapses those case-insensitively in the *request* and
    // echoes back only one spelling, so the response won't have a literal
    // "abc.l" key even though it did resolve that ticker.
    mockGetInstrumentBatch.mockResolvedValue({
      instruments: { 'ABC.L': { prices: [{ date: '2024-01-01', close: 1 }] } },
      empty: [],
      unknown: [],
    });

    const missing = await preloadInstrumentHistory(['ABC.L', 'abc.l'], 30);

    expect(missing).toEqual([]);
    expect(getCachedInstrumentHistory('ABC.L', 30)?.prices).toEqual([
      { date: '2024-01-01', close: 1 },
    ]);
    expect(getCachedInstrumentHistory('abc.l', 30)?.prices).toEqual([
      { date: '2024-01-01', close: 1 },
    ]);
  });

  it('prefers the instruments bucket over empty for a malformed dual-bucket response', async () => {
    // The backend's partition contract guarantees a ticker lands in exactly one
    // bucket, but this shouldn't crash or misclassify if that's ever violated.
    mockGetInstrumentBatch.mockResolvedValue({
      instruments: { 'A.L': { prices: [{ date: '2024-01-01', close: 1 }] } },
      empty: ['A.L'],
      unknown: [],
    });

    const missing = await preloadInstrumentHistory(['A.L'], 30);

    expect(missing).toEqual([]);
    expect(getCachedInstrumentHistory('A.L', 30)?.prices).toEqual([
      { date: '2024-01-01', close: 1 },
    ]);
  });

  it('retries an unknown ticker on a later call instead of pinning the miss', async () => {
    mockGetInstrumentBatch
      .mockResolvedValueOnce({ instruments: {}, empty: [], unknown: ['A.L'] })
      .mockResolvedValueOnce({
        instruments: { 'A.L': { prices: [{ date: '2024-01-01', close: 1 }] } },
        empty: [],
        unknown: [],
      });

    await preloadInstrumentHistory(['A.L'], 30);
    const missing = await preloadInstrumentHistory(['A.L'], 30);

    expect(mockGetInstrumentBatch).toHaveBeenCalledTimes(2);
    expect(missing).toEqual([]);
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

  it('splits into multiple batch calls past the 100-ticker backend cap', async () => {
    const tickers = Array.from({ length: 150 }, (_, i) => `T${i}.L`);
    mockGetInstrumentBatch.mockImplementation(async (group: string[]) => ({
      instruments: Object.fromEntries(
        group.map((t) => [t, { prices: [{ date: '2024-01-01', close: 1 }] }]),
      ),
      empty: [],
      unknown: [],
    }));

    const missing = await preloadInstrumentHistory(tickers, 30);

    expect(mockGetInstrumentBatch).toHaveBeenCalledTimes(2);
    const [firstGroup] = mockGetInstrumentBatch.mock.calls[0];
    const [secondGroup] = mockGetInstrumentBatch.mock.calls[1];
    expect(firstGroup).toHaveLength(100);
    expect(secondGroup).toHaveLength(50);
    expect(new Set([...firstGroup, ...secondGroup])).toEqual(new Set(tickers));
    expect(missing).toEqual([]);
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
