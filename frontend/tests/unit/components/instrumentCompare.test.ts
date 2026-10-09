import { describe, it, expect } from "vitest";
import { buildCompareRows } from "@/components/instrumentCompare";

describe("buildCompareRows", () => {
  it("rebases every series to 0% on the first date they all share", () => {
    const rows = buildCompareRows([
      {
        ticker: "AAA.L",
        points: [
          { date: "2024-01-01", close: 50 },
          { date: "2024-01-02", close: 100 },
          { date: "2024-01-03", close: 110 },
        ],
      },
      {
        ticker: "BBB.L",
        points: [
          { date: "2024-01-02", close: 20 },
          { date: "2024-01-03", close: 18 },
        ],
      },
    ]);

    expect(rows.map((r) => r.date)).toEqual(["2024-01-02", "2024-01-03"]);
    expect(rows[0]).toMatchObject({ s0: 0, s1: 0 });
    expect(rows[1].s0 as number).toBeCloseTo(10);
    expect(rows[1].s1 as number).toBeCloseTo(-10);
  });

  it("leaves a series' value off dates it has no price for", () => {
    const rows = buildCompareRows([
      {
        ticker: "AAA.L",
        points: [
          { date: "2024-01-01", close: 100 },
          { date: "2024-01-02", close: 101 },
        ],
      },
      { ticker: "BBB.L", points: [{ date: "2024-01-01", close: 10 }] },
    ]);

    expect(rows[1]).toEqual({ date: "2024-01-02", s0: expect.closeTo(1) });
  });

  it("returns nothing when a series has no usable prices", () => {
    expect(
      buildCompareRows([
        { ticker: "AAA.L", points: [{ date: "2024-01-01", close: 100 }] },
        { ticker: "BBB.L", points: [{ date: "2024-01-01", close: 0 }] },
      ]),
    ).toEqual([]);
  });
});
