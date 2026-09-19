import { describe, expect, it } from "vitest";

import {
  BUY_MARKER_COLOR,
  SELL_MARKER_COLOR,
  buildTradeMarkers,
  capMarkers,
  matchesTicker,
  snapToChartDate,
  tradeSide,
  type TradeMarker,
} from "@/components/instrumentTradeMarkers";
import type { Transaction } from "@/types";

const tx = (over: Partial<Transaction> = {}): Transaction => ({
  owner: "alice",
  account: "isa",
  date: "2024-03-04",
  ticker: "AAPL.N",
  type: "BUY",
  ...over,
});

const CHART_DATES = [
  "2024-03-01",
  "2024-03-04",
  "2024-03-05",
  "2024-03-06",
  "2024-03-07",
];

describe("tradeSide", () => {
  it("classifies buys and sells regardless of case", () => {
    expect(tradeSide({ type: "BUY", kind: null })).toBe("buy");
    expect(tradeSide({ type: "buy", kind: null })).toBe("buy");
    expect(tradeSide({ type: "SELL", kind: null })).toBe("sell");
    expect(tradeSide({ type: "sell", kind: null })).toBe("sell");
  });

  it("falls back to kind when type is absent", () => {
    expect(tradeSide({ type: null, kind: "Sell" })).toBe("sell");
  });

  it("ignores transactions that are not purchases or sales", () => {
    expect(tradeSide({ type: "DIVIDEND", kind: null })).toBeNull();
    expect(tradeSide({ type: "FEE", kind: null })).toBeNull();
    expect(tradeSide({ type: null, kind: null })).toBeNull();
  });
});

describe("matchesTicker", () => {
  it("matches across differing exchange suffixes and case", () => {
    expect(matchesTicker("AAPL", "AAPL.N")).toBe(true);
    expect(matchesTicker("aapl.n", "AAPL.N")).toBe(true);
    expect(matchesTicker("AAPL.L", "AAPL.N")).toBe(true);
  });

  it("rejects a different instrument or a missing ticker", () => {
    expect(matchesTicker("MSFT", "AAPL.N")).toBe(false);
    expect(matchesTicker(null, "AAPL.N")).toBe(false);
    expect(matchesTicker("", "AAPL.N")).toBe(false);
  });
});

describe("snapToChartDate", () => {
  it("keeps a trade date that is already a chart point", () => {
    expect(snapToChartDate("2024-03-05", CHART_DATES)).toBe("2024-03-05");
  });

  it("snaps a non-trading day onto the nearest chart point", () => {
    // 2024-03-02 is a Saturday: closer to 03-01 than to 03-04.
    expect(snapToChartDate("2024-03-02", CHART_DATES)).toBe("2024-03-01");
    // 2024-03-03 is a Sunday: closer to 03-04.
    expect(snapToChartDate("2024-03-03", CHART_DATES)).toBe("2024-03-04");
  });

  it("drops trades outside the charted range rather than clamping them", () => {
    expect(snapToChartDate("2020-01-01", CHART_DATES)).toBeNull();
    expect(snapToChartDate("2030-01-01", CHART_DATES)).toBeNull();
  });

  it("returns null when there is no price history", () => {
    expect(snapToChartDate("2024-03-04", [])).toBeNull();
  });

  // Rows converted from the portfolio XML carry a full timestamp
  // (e.g. "2019-08-27T00:00") rather than a plain date.
  it("handles trade dates carrying a time component", () => {
    expect(snapToChartDate("2024-03-05T00:00", CHART_DATES)).toBe("2024-03-05");
  });

  it("keeps a timestamped trade on the last charted day", () => {
    expect(snapToChartDate("2024-03-07T00:00", CHART_DATES)).toBe("2024-03-07");
  });

  it("keeps a timestamped trade on the first charted day", () => {
    expect(snapToChartDate("2024-03-01T09:30", CHART_DATES)).toBe("2024-03-01");
  });
});

describe("capMarkers", () => {
  const marker = (i: number, side: "buy" | "sell"): TradeMarker => ({
    key: `k${i}`,
    date: `2024-03-${String(i).padStart(2, "0")}`,
    tradeDate: `2024-03-${String(i).padStart(2, "0")}`,
    side,
    owner: "alice",
    account: "isa",
    units: 1,
    price: 1,
  });

  it("leaves a modest number of markers untouched", () => {
    const markers = [marker(1, "buy"), marker(2, "sell")];
    expect(capMarkers(markers, 12)).toHaveLength(2);
  });

  it("collapses a heavily traded instrument to the first and last of each side", () => {
    const markers = [
      ...Array.from({ length: 10 }, (_, i) => marker(i + 1, "buy")),
      ...Array.from({ length: 10 }, (_, i) => marker(i + 11, "sell")),
    ];

    const capped = capMarkers(markers, 12);

    expect(capped).toHaveLength(4);
    expect(capped.map((m) => m.key)).toEqual(["k1", "k10", "k11", "k20"]);
  });

  it("keeps the span of a single-sided history", () => {
    const markers = Array.from({ length: 20 }, (_, i) => marker(i + 1, "buy"));

    const capped = capMarkers(markers, 12);

    expect(capped.map((m) => m.key)).toEqual(["k1", "k20"]);
  });
});

describe("buildTradeMarkers", () => {
  it("marks a buy green and a sell red", () => {
    const markers = buildTradeMarkers(
      [
        tx({ id: "1", date: "2024-03-04", type: "BUY" }),
        tx({ id: "2", date: "2024-03-06", type: "SELL" }),
      ],
      "AAPL.N",
      CHART_DATES,
    );

    expect(markers).toHaveLength(2);
    expect(markers[0].side).toBe("buy");
    expect(markers[1].side).toBe("sell");
    // Guards the colour constants the chart renders these markers with.
    expect(BUY_MARKER_COLOR).toBe("#22c55e");
    expect(SELL_MARKER_COLOR).toBe("#ef4444");
  });

  it("excludes trades in other instruments", () => {
    const markers = buildTradeMarkers(
      [tx({ id: "1" }), tx({ id: "2", ticker: "MSFT.N" })],
      "AAPL.N",
      CHART_DATES,
    );

    expect(markers.map((m) => m.key)).toEqual(["1"]);
  });

  it("excludes trades outside the selected range", () => {
    const markers = buildTradeMarkers(
      [tx({ id: "1" }), tx({ id: "2", date: "2019-06-01" })],
      "AAPL.N",
      CHART_DATES,
    );

    expect(markers.map((m) => m.key)).toEqual(["1"]);
  });

  it("merges trades from several owners and accounts onto one chart", () => {
    const markers = buildTradeMarkers(
      [
        tx({ id: "1", owner: "alice", account: "isa" }),
        tx({ id: "2", owner: "bob", account: "sipp", date: "2024-03-06" }),
      ],
      "AAPL.N",
      CHART_DATES,
    );

    expect(markers.map((m) => `${m.owner}/${m.account}`)).toEqual([
      "alice/isa",
      "bob/sipp",
    ]);
  });

  it("orders markers by trade date", () => {
    const markers = buildTradeMarkers(
      [
        tx({ id: "late", date: "2024-03-07" }),
        tx({ id: "early", date: "2024-03-01" }),
      ],
      "AAPL.N",
      CHART_DATES,
    );

    expect(markers.map((m) => m.key)).toEqual(["early", "late"]);
  });

  it("records the original trade date alongside the snapped chart date", () => {
    const markers = buildTradeMarkers(
      [tx({ id: "1", date: "2024-03-03" })],
      "AAPL.N",
      CHART_DATES,
    );

    expect(markers[0].tradeDate).toBe("2024-03-03");
    expect(markers[0].date).toBe("2024-03-04");
  });

  it("returns nothing for an instrument with no trade history", () => {
    expect(buildTradeMarkers([], "AAPL.N", CHART_DATES)).toEqual([]);
  });

  // Real rows converted from the portfolio XML identify the instrument only by
  // `security_ref`, an index into that XML.  They cannot be attributed to a
  // ticker here, so they must be skipped rather than guessed at.
  it("skips rows that identify the instrument only by security_ref", () => {
    const markers = buildTradeMarkers(
      [
        {
          owner: "steve",
          account: "isa",
          date: "2024-03-04T00:00",
          type: "BUY",
          security_ref: "22",
          ticker: null,
        },
      ],
      "AAPL.N",
      CHART_DATES,
    );

    expect(markers).toEqual([]);
  });

  it("marks a timestamped trade on the last charted day", () => {
    const markers = buildTradeMarkers(
      [tx({ id: "1", date: "2024-03-07T00:00" })],
      "AAPL.N",
      CHART_DATES,
    );

    expect(markers.map((m) => m.date)).toEqual(["2024-03-07"]);
  });

  it("falls back to a synthesised key when the row has no id", () => {
    const markers = buildTradeMarkers(
      [tx({ id: null, external_id: null })],
      "AAPL.N",
      CHART_DATES,
    );

    expect(markers[0].key).toBe("alice-isa-2024-03-04-0");
  });
});
