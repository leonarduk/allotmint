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

  it("keeps share-class and unknown suffixes distinct (#7798)", () => {
    expect(matchesTicker("BRK.A", "BRK.B")).toBe(false);
    expect(matchesTicker("BRK.B", "BRK.B")).toBe(true);
    expect(matchesTicker("brk.b", "BRK.B.N")).toBe(true);
    expect(matchesTicker("FOO.XYZ", "FOO")).toBe(false);
    expect(matchesTicker("FOO.XYZ", "FOO.XYZ")).toBe(true);
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

  const buys = (n: number, from = 1) =>
    Array.from({ length: n }, (_, i) => marker(i + from, "buy"));
  const sells = (n: number, from = 1) =>
    Array.from({ length: n }, (_, i) => marker(i + from, "sell"));

  it("leaves a history exactly at the cap untouched", () => {
    const markers = buys(12);
    expect(capMarkers(markers, 12)).toBe(markers);
  });

  it("splits the budget evenly between balanced sides, thinning each evenly (#7797)", () => {
    const capped = capMarkers([...buys(10), ...sells(10, 11)], 12);

    expect(capped.map((m) => m.key)).toEqual([
      "k1", "k3", "k5", "k6", "k8", "k10",
      "k11", "k13", "k15", "k16", "k18", "k20",
    ]);
  });

  it("keeps all but one of 13 one-sided buys rather than just two (#7797)", () => {
    const capped = capMarkers(buys(13), 12);

    expect(capped).toHaveLength(12);
    expect(capped[0].key).toBe("k1");
    expect(capped[capped.length - 1].key).toBe("k13");
  });

  it("gives a one-sided history the whole budget and keeps its span", () => {
    const capped = capMarkers(buys(20), 12);

    expect(capped).toHaveLength(12);
    expect(new Set(capped.map((m) => m.key)).size).toBe(12);
    expect(capped[0].key).toBe("k1");
    expect(capped[capped.length - 1].key).toBe("k20");
  });

  it("allocates in proportion to counts but never starves the smaller side", () => {
    const capped = capMarkers([...buys(30), ...sells(3, 31)], 12);
    const bySide = (side: string) => capped.filter((m) => m.side === side);

    expect(capped).toHaveLength(12);
    expect(bySide("sell").map((m) => m.key)).toEqual(["k31", "k33"]);
    expect(bySide("buy")).toHaveLength(10);
  });

  it("hands budget a small side cannot use to the other side", () => {
    const capped = capMarkers([...buys(20), ...sells(1, 21)], 12);

    expect(capped.filter((m) => m.side === "sell")).toHaveLength(1);
    expect(capped.filter((m) => m.side === "buy")).toHaveLength(11);
  });

  it("returns the merged result sorted by trade date", () => {
    // Interleave sides so a naive buys-then-sells concat would be out of order.
    const markers = Array.from({ length: 20 }, (_, i) =>
      marker(i + 1, i % 2 === 0 ? "buy" : "sell"),
    );

    const dates = capMarkers(markers, 12).map((m) => m.tradeDate);

    expect(dates).toEqual([...dates].sort());
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

  // Reconciliation injects balancing rows, dated a year in the past, when a
  // holding cannot be explained by the recorded trades.  Drawing them would
  // claim a trade happened on a date it did not.
  it("skips synthetic reconciliation rows", () => {
    const markers = buildTradeMarkers(
      [
        tx({ id: "real", date: "2024-03-04" }),
        tx({ id: "balancing", date: "2024-03-06", synthetic: true }),
      ],
      "AAPL.N",
      CHART_DATES,
    );

    expect(markers.map((m) => m.key)).toEqual(["real"]);
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

  it("reports real units: units first, else PP shares / 10^8 (#10203)", () => {
    const markers = buildTradeMarkers(
      [
        tx({ id: "pp", date: "2024-03-04", shares: 1_000_000_000 }),
        tx({ id: "edited", date: "2024-03-05", units: 4, shares: 1_000_000_000 }),
        tx({ id: "manual", date: "2024-03-06", units: 2_000_000 }),
        tx({ id: "none", date: "2024-03-07" }),
      ],
      "AAPL.N",
      CHART_DATES,
    );

    expect(Object.fromEntries(markers.map((m) => [m.key, m.units]))).toEqual({
      pp: 10,
      edited: 4,
      manual: 2_000_000,
      none: null,
    });
  });
});
