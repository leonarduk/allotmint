import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  preloadInstrumentHistory,
  getCachedInstrumentHistory,
  __clearInstrumentHistoryCache,
} from "@/hooks/useInstrumentHistory";

const detailWithHistory = {
  prices: [{ date: "2024-01-01", close: 10 }],
  positions: [],
  rows: 1,
};

const detailWithoutHistory = {
  prices: [],
  positions: [],
  rows: 0,
};

function stubInstrumentFetch(
  responses: Record<string, { prices: unknown[] }>,
) {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.toString()
          : (input as Request).url;
    const match = url.match(/ticker=([^&]+)/);
    const ticker = match ? decodeURIComponent(match[1]) : "";
    const detail = responses[ticker] ?? detailWithoutHistory;
    return Promise.resolve({
      ok: true,
      json: async () => detail,
    } as Response);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("preloadInstrumentHistory", () => {
  beforeEach(() => {
    __clearInstrumentHistoryCache();
    vi.unstubAllGlobals();
  });

  it("returns tickers that resolved to an empty history", async () => {
    stubInstrumentFetch({
      "A.L": detailWithoutHistory,
      "B.L": detailWithHistory,
      "C.L": detailWithoutHistory,
    });

    const missing = await preloadInstrumentHistory(["A.L", "B.L", "C.L"], 30);

    expect(missing).toEqual(["A.L", "C.L"]);
  });

  it("caches empty responses so later preloads do not refetch", async () => {
    const fetchMock = stubInstrumentFetch({ "A.L": detailWithoutHistory });

    await preloadInstrumentHistory(["A.L"], 30);
    const missing = await preloadInstrumentHistory(["A.L"], 30);

    const instrumentCalls = fetchMock.mock.calls.filter(([input]) =>
      String(input).includes("/instrument/"),
    );
    expect(instrumentCalls).toHaveLength(1);
    expect(missing).toEqual(["A.L"]);
    expect(getCachedInstrumentHistory("A.L", 30)?.prices).toEqual([]);
  });

  it("ignores failed fetches (e.g. unknown tickers) in the notice set", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: false,
          status: 404,
          json: async () => ({ detail: "No price history available" }),
        } as Response),
      ),
    );

    const missing = await preloadInstrumentHistory(["A.L"], 30);

    expect(missing).toEqual([]);
  });

  it("deduplicates tickers passed multiple times", async () => {
    const fetchMock = stubInstrumentFetch({
      "A.L": detailWithoutHistory,
      "B.L": detailWithHistory,
    });

    const missing = await preloadInstrumentHistory(
      ["A.L", "A.L", "B.L"],
      30,
    );

    const instrumentCalls = fetchMock.mock.calls.filter(([input]) =>
      String(input).includes("/instrument/"),
    );
    expect(instrumentCalls).toHaveLength(2);
    expect(missing).toEqual(["A.L"]);
  });
});
