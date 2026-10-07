import { describe, it, expect } from "vitest";
import { buildCumulativeComparison } from "@/lib/benchmarkSeries";

describe("buildCumulativeComparison (#7833)", () => {
  it("pairs portfolio and benchmark on the same dates", () => {
    expect(
      buildCumulativeComparison([
        {
          date: "2024-03-01",
          portfolio_cumulative_return: 0.01,
          benchmark_cumulative_return: 0.02,
          excess_cumulative_return: -0.01,
        },
        {
          date: "2024-03-04",
          portfolio_cumulative_return: 0.03,
          benchmark_cumulative_return: 0.025,
          excess_cumulative_return: 0.005,
        },
      ]),
    ).toEqual([
      { date: "2024-03-01", portfolio: 0.01, benchmark: 0.02 },
      { date: "2024-03-04", portfolio: 0.03, benchmark: 0.025 },
    ]);
  });

  it("drops a date entirely when either side is non-finite, never one line alone", () => {
    const out = buildCumulativeComparison([
      {
        date: "2024-03-01",
        portfolio_cumulative_return: Number.NaN,
        benchmark_cumulative_return: 0.02,
        excess_cumulative_return: 0,
      },
      {
        date: "2024-03-04",
        portfolio_cumulative_return: 0.03,
        benchmark_cumulative_return: Number.POSITIVE_INFINITY,
        excess_cumulative_return: 0,
      },
      {
        date: "2024-03-05",
        portfolio_cumulative_return: 0.04,
        benchmark_cumulative_return: 0.03,
        excess_cumulative_return: 0.01,
      },
    ]);
    expect(out.map((p) => p.date)).toEqual(["2024-03-05"]);
  });

  it("returns an empty array for missing or empty series", () => {
    expect(buildCumulativeComparison(undefined)).toEqual([]);
    expect(buildCumulativeComparison(null)).toEqual([]);
    expect(buildCumulativeComparison([])).toEqual([]);
  });
});
