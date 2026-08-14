import { renderHook, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterAll, afterEach } from 'vitest';
// Mock the API module so we can reliably intercept calls across ESM boundaries
vi.mock('@/api', () => ({
  fetchInstrumentDetailWithRetry: vi.fn(),
}));
import * as api from '@/api';
import {
  useInstrumentHistory,
  preloadInstrumentHistory,
  __clearInstrumentHistoryCache,
} from '@/hooks/useInstrumentHistory';

const mockGetInstrumentDetail = api
  .fetchInstrumentDetailWithRetry as unknown as ReturnType<typeof vi.fn>;

afterAll(() => {
  mockGetInstrumentDetail.mockRestore();
});

describe('useInstrumentHistory', () => {
  beforeEach(() => {
    mockGetInstrumentDetail.mockReset();
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

  it('shares one in-flight fetch across concurrent preload callers', async () => {
    mockGetInstrumentDetail.mockResolvedValue({
      mini: { 7: [], 30: [], 180: [] },
      positions: [],
    });

    await Promise.all([
      preloadInstrumentHistory(['ABC', 'DEF'], 30),
      preloadInstrumentHistory(['ABC', 'DEF'], 30),
    ]);

    expect(mockGetInstrumentDetail).toHaveBeenCalledTimes(2);
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
});
