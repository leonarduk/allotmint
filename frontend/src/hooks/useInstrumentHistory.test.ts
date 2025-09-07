import { renderHook, waitFor } from "@testing-library/react";
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
});
