import { renderHook, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../api", () => ({
  getInstrumentDetail: vi.fn(),
}));
import { getInstrumentDetail } from "../api";
import { useInstrumentHistory } from "./useInstrumentHistory";

const mockGetInstrumentDetail = getInstrumentDetail as unknown as vi.Mock;

describe("useInstrumentHistory", () => {
  beforeEach(() => {
    mockGetInstrumentDetail.mockReset();
  });

  it("retries on HTTP 429 responses", async () => {
    mockGetInstrumentDetail.mockRejectedValue(
      new Error("HTTP 429 – Too Many Requests"),
    );

    const { result } = renderHook(() => useInstrumentHistory("ABC", 7));

    await waitFor(() => expect(result.current.error).toBeTruthy(), {
      timeout: 10000,
    });

    expect(mockGetInstrumentDetail).toHaveBeenCalledTimes(3);
  });

  it("uses Retry-After header for backoff", async () => {
    vi.useFakeTimers();
    const randSpy = vi.spyOn(Math, "random").mockReturnValue(0);

    const err = new Error("HTTP 429 – Too Many Requests") as any;
    err.response = { headers: new Headers({ "Retry-After": "2" }) };

    mockGetInstrumentDetail
      .mockRejectedValueOnce(err)
      .mockResolvedValueOnce({ mini: { 7: [], 30: [], 180: [] } });

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
});
