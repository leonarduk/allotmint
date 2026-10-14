import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ADMIN_WARMING_POLL_MS, useAdminScan } from '@/hooks/useAdminScan';

describe('useAdminScan (#10754)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('re-polls while the backend is warming and stops once the list is complete', async () => {
    const load = vi
      .fn()
      .mockResolvedValueOnce({ data: ['a'], warming: true })
      .mockResolvedValueOnce({ data: ['a', 'b'], warming: true })
      .mockResolvedValueOnce({ data: ['a', 'b', 'c'], warming: false });
    const onData = vi.fn();
    const { result } = renderHook(() => useAdminScan(load, onData, vi.fn()));

    await act(async () => {});
    expect(onData).toHaveBeenLastCalledWith(['a'], true);
    expect(result.current.warming).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(ADMIN_WARMING_POLL_MS);
    });
    expect(onData).toHaveBeenLastCalledWith(['a', 'b'], true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(ADMIN_WARMING_POLL_MS);
    });
    expect(onData).toHaveBeenLastCalledWith(['a', 'b', 'c'], false);
    expect(result.current.warming).toBe(false);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(ADMIN_WARMING_POLL_MS * 3);
    });
    expect(load).toHaveBeenCalledTimes(3);
  });

  it('does not poll when the first result is already complete', async () => {
    const load = vi.fn().mockResolvedValue({ data: [], warming: false });
    renderHook(() => useAdminScan(load, vi.fn(), vi.fn()));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(ADMIN_WARMING_POLL_MS * 3);
    });
    expect(load).toHaveBeenCalledTimes(1);
  });

  it('reports a failed load, including one that throws synchronously, and stops polling', async () => {
    const boom = new Error('boom');
    const load = vi.fn(() => {
      throw boom;
    });
    const onError = vi.fn();
    const { result } = renderHook(() => useAdminScan(load, vi.fn(), onError));

    await act(async () => {});
    expect(onError).toHaveBeenCalledWith(boom);
    expect(result.current.warming).toBe(false);
  });

  it('stops polling after unmount', async () => {
    const load = vi.fn().mockResolvedValue({ data: [], warming: true });
    const { unmount } = renderHook(() => useAdminScan(load, vi.fn(), vi.fn()));

    await act(async () => {});
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ADMIN_WARMING_POLL_MS * 3);
    });
    expect(load).toHaveBeenCalledTimes(1);
  });

  it('reload starts a fresh load', async () => {
    const load = vi.fn().mockResolvedValue({ data: [], warming: false });
    const { result } = renderHook(() => useAdminScan(load, vi.fn(), vi.fn()));

    await act(async () => {});
    act(() => result.current.reload());
    await act(async () => {});
    expect(load).toHaveBeenCalledTimes(2);
  });
});
