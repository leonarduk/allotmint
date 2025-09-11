import { renderHook, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterAll } from "vitest";
import * as api from "../api";
import {
  useInstrumentHistory,
  __clearInstrumentHistoryCache,
} from "./useInstrumentHistory";

const mockGetInstrumentDetail = vi.spyOn(api, "getInstrumentDetail");

afterAll(() => {
  mockGetInstrumentDetail.mockRestore();
});

describe("useInstrumentHistory", () => {
  beforeEach(() => {
    mockGetInstrumentDetail.mockReset();
    __clearInstrumentHistoryCache();
  });

  it("retries on HTTP 429 responses", async () => {
    vi.useFakeTimers();
    mockGetInstrumentDetail.mockRejectedValue(
      new Error("HTTP 429 – Too Many Requests"),
    );

    const { result } = renderHook(() => useInstrumentHistory("ABC", 7));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(mockGetInstrumentDetail).toHaveBeenCalledTimes(3);
    expect(result.current.error).toBeTruthy();

    vi.useRealTimers();
  });

  it("uses Retry-After header for backoff", async () => {
    vi.useFakeTimers();
    const randSpy = vi.spyOn(Math, "random").mockReturnValue(0);

    const err = new Error("HTTP 429 – Too Many Requests") as any;
    err.response = { headers: new Headers({ "Retry-After": "2" }) };

    mockGetInstrumentDetail
      .mockRejectedValueOnce(err)
      .mockResolvedValueOnce({ mini: { 7: [], 30: [], 180: [] }, positions: [] });

    const { result } = renderHook(() => useInstrumentHistory("ABC", 7));

    expect(mockGetInstrumentDetail).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(mockGetInstrumentDetail).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(mockGetInstrumentDetail).toHaveBeenCalledTimes(2);
    expect(result.current.data).not.toBeNull();

    randSpy.mockRestore();
    vi.useRealTimers();
  });

  it("caches detail per ticker regardless of day range", async () => {
    mockGetInstrumentDetail.mockResolvedValue({
      mini: { 7: [], 30: [], 180: [], 365: [] },
      positions: [],
    });

    const { result, rerender } = renderHook(
      ({ days }) => useInstrumentHistory("ABC", days),
      { initialProps: { days: 7 } },
    );

    await waitFor(() => expect(result.current.data).not.toBeNull());
    expect(mockGetInstrumentDetail).toHaveBeenCalledTimes(1);

    rerender({ days: 30 });
    await waitFor(() => expect(result.current.data).not.toBeNull());
    expect(mockGetInstrumentDetail).toHaveBeenCalledTimes(1);
  });
});
