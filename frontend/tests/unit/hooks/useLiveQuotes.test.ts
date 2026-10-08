import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/api', () => ({
  getLiveQuotes: vi.fn(),
}));

import * as api from '@/api';
import type { LiveQuote } from '@/api';
import { LIVE_QUOTE_BATCH_SIZE, useLiveQuotes } from '@/hooks/useLiveQuotes';

const mockGetLiveQuotes = vi.mocked(api.getLiveQuotes);

const quote = (price: number): LiveQuote => ({
  price,
  price_gbp: price,
  currency: 'GBP',
  previous_close: null,
  change_pct: null,
  timestamp: '2024-01-02T10:15:00Z',
  market_state: 'REGULAR',
  is_stale: false,
});

describe('useLiveQuotes', () => {
  beforeEach(() => {
    mockGetLiveQuotes.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('requests deduplicated, upper-cased tickers once and returns the quotes', async () => {
    mockGetLiveQuotes.mockResolvedValue({ quotes: { 'VOD.L': quote(0.72) } });

    const { result } = renderHook(() => useLiveQuotes(['vod.l', 'VOD.L', ' ']));

    await waitFor(() => expect(result.current['VOD.L']?.price).toBe(0.72));
    expect(mockGetLiveQuotes).toHaveBeenCalledTimes(1);
    expect(mockGetLiveQuotes.mock.calls[0][0]).toEqual(['VOD.L']);
  });

  it('keeps the previous quotes while a changed ticker list re-polls', async () => {
    let release: (v: { quotes: Record<string, LiveQuote> }) => void = () => {};
    mockGetLiveQuotes
      .mockResolvedValueOnce({ quotes: { 'VOD.L': quote(0.72) } })
      .mockImplementationOnce(
        () => new Promise((resolve) => (release = resolve))
      );

    const { result, rerender } = renderHook(
      ({ tickers }) => useLiveQuotes(tickers),
      {
        initialProps: { tickers: ['VOD.L'] },
      }
    );
    await waitFor(() => expect(result.current['VOD.L']?.price).toBe(0.72));

    rerender({ tickers: ['VOD.L', 'BP.L'] });
    expect(result.current['VOD.L']?.price).toBe(0.72);

    await act(async () => {
      release({ quotes: { 'VOD.L': quote(0.73), 'BP.L': quote(4.5) } });
    });
    expect(result.current['BP.L']?.price).toBe(4.5);
  });

  it('does nothing without tickers', () => {
    const { result } = renderHook(() => useLiveQuotes([]));
    expect(result.current).toEqual({});
    expect(mockGetLiveQuotes).not.toHaveBeenCalled();
  });

  it('splits large ticker lists into endpoint-sized batches and merges them', async () => {
    const tickers = Array.from(
      { length: LIVE_QUOTE_BATCH_SIZE + 5 },
      (_, i) => `T${i}.L`
    );
    mockGetLiveQuotes.mockImplementation(async (batch: string[]) => ({
      quotes: { [batch[0]]: quote(batch.length) },
    }));

    const { result } = renderHook(() => useLiveQuotes(tickers));

    await waitFor(() => expect(Object.keys(result.current)).toHaveLength(2));
    expect(mockGetLiveQuotes).toHaveBeenCalledTimes(2);
    expect(
      mockGetLiveQuotes.mock.calls
        .map(([batch]) => batch.length)
        .sort((a, b) => a - b)
    ).toEqual([5, LIVE_QUOTE_BATCH_SIZE]);
  });

  it('re-polls on the interval and keeps the last quotes when a poll fails', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    mockGetLiveQuotes
      .mockResolvedValueOnce({ quotes: { 'VOD.L': quote(0.72) } })
      .mockRejectedValueOnce(new Error('502'));

    const { result } = renderHook(() => useLiveQuotes(['VOD.L'], 1_000));
    await waitFor(() => expect(result.current['VOD.L']?.price).toBe(0.72));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });

    expect(mockGetLiveQuotes).toHaveBeenCalledTimes(2);
    expect(result.current['VOD.L']?.price).toBe(0.72);
  });
});
