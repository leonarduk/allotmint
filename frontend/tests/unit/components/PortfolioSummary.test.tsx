import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import {
  PortfolioSummary,
  computePortfolioTotals,
} from "@/components/PortfolioSummary";
import type { Account, Holding } from "@/types";

function holding(overrides: Partial<Holding>): Holding {
  return {
    ticker: "ABC.L",
    name: "Test Holding",
    units: 10,
    market_value_gbp: 100,
    cost_basis_gbp: 80,
    effective_cost_basis_gbp: 80,
    gain_gbp: 20,
    gain_pct: 25,
    cost_basis_source: "book",
    ...overrides,
  };
}

function account(holdings: Holding[]): Account {
  const value_estimate_gbp = holdings.reduce(
    (sum, h) => sum + (h.market_value_gbp ?? 0),
    0,
  );
  return {
    account_type: "ISA",
    currency: "GBP",
    value_estimate_gbp,
    holdings,
  };
}

describe("computePortfolioTotals", () => {
  it("sums known holdings the same way as before #7220", () => {
    const accounts = [
      account([
        holding({ ticker: "AAA.L", market_value_gbp: 100, cost_basis_gbp: 80, gain_gbp: 20 }),
        holding({ ticker: "BBB.L", market_value_gbp: 50, cost_basis_gbp: 60, gain_gbp: -10 }),
      ]),
    ];
    const totals = computePortfolioTotals(accounts);
    expect(totals.totalGain).toBe(10);
    expect(totals.totalCost).toBe(140);
    expect(totals.unknownCostBasisCount).toBe(0);
    expect(totals.gainEligibleHoldingCount).toBe(2);
  });

  it("excludes unknown-cost-basis holdings from gain/cost but still counts their market value (#7220)", () => {
    const accounts = [
      account([
        // A holding with real gain data.
        holding({ ticker: "AAA.L", market_value_gbp: 100, cost_basis_gbp: 80, gain_gbp: 20 }),
        // A holding with no acquisition date / no booked cost: the backend
        // sets cost == market value (fabricated), gain == 0. Must not be
        // summed into totalGain/totalCost as a real zero.
        holding({
          ticker: "ZZZ.L",
          market_value_gbp: 500,
          cost_basis_gbp: 0,
          effective_cost_basis_gbp: 500,
          gain_gbp: 0,
          gain_pct: 0,
          cost_basis_source: "unknown",
        }),
      ]),
    ];
    const totals = computePortfolioTotals(accounts);

    // The known holding's real gain must survive untouched.
    expect(totals.totalGain).toBe(20);
    expect(totals.totalCost).toBe(80);
    // But the unknown holding's market value still counts toward stock value.
    expect(totals.totalStockValue).toBe(600);
    expect(totals.unknownCostBasisCount).toBe(1);
    expect(totals.gainEligibleHoldingCount).toBe(2);
  });

  it("excludes book_suspect holdings from gain/cost so a tiny suspect book cost can't inflate the total (#8472)", () => {
    const accounts = [
      account([
        holding({ ticker: "AAA.L", market_value_gbp: 100, cost_basis_gbp: 80, gain_gbp: 20 }),
        // 50 units booked at £263 but worth £33,620: backend nulls the gain.
        holding({
          ticker: "AV.L",
          market_value_gbp: 33620,
          cost_basis_gbp: 263,
          effective_cost_basis_gbp: 263,
          gain_gbp: null,
          gain_pct: null,
          cost_basis_source: "book_suspect",
        }),
      ]),
    ];
    const totals = computePortfolioTotals(accounts);

    expect(totals.totalGain).toBe(20);
    expect(totals.totalCost).toBe(80);
    expect(totals.totalGainPct).toBe(25);
    expect(totals.totalStockValue).toBe(33720);
    expect(totals.unknownCostBasisCount).toBe(1);
  });

  it("still includes cash holdings' real cost/gain, unlike unknown holdings", () => {
    const accounts = [
      account([
        holding({
          ticker: "CASH.GBP",
          name: "Cash (GBP)",
          instrument_type: "cash",
          market_value_gbp: 1000,
          cost_basis_gbp: 1000,
          effective_cost_basis_gbp: 1000,
          gain_gbp: 0,
          gain_pct: 0,
          cost_basis_source: "cash",
        }),
      ]),
    ];
    const totals = computePortfolioTotals(accounts);
    expect(totals.totalCash).toBe(1000);
    // Cash's real (non-fabricated) cost basis is still summed into totalCost,
    // matching pre-#7220 behaviour -- only cost_basis_source === "unknown"
    // is excluded.
    expect(totals.totalCost).toBe(1000);
    expect(totals.unknownCostBasisCount).toBe(0);
  });

  it("excludes unpriced non-cash holdings from gain/cost instead of booking their cost as a loss (#8607)", () => {
    const accounts = [
      account([
        holding({ ticker: "AAA.L", market_value_gbp: 100, cost_basis_gbp: 80, gain_gbp: 20 }),
        // No price: market value is null and the backend nulls the gain.
        holding({
          ticker: "NOPRICE.L",
          market_value_gbp: null,
          cost_basis_gbp: 1000,
          effective_cost_basis_gbp: 1000,
          gain_gbp: null,
          gain_pct: null,
        }),
      ]),
    ];
    const totals = computePortfolioTotals(accounts);

    expect(totals.totalGain).toBe(20);
    expect(totals.totalCost).toBe(80);
    expect(totals.totalGainPct).toBe(25);
    expect(totals.totalStockValue).toBe(100);
    expect(totals.unpricedHoldingCount).toBe(1);
    expect(totals.unknownCostBasisCount).toBe(0);
    expect(totals.gainEligibleHoldingCount).toBe(2);
  });
});

describe("PortfolioSummary", () => {
  it("renders a confident gain figure when every holding's cost basis is known", () => {
    const totals = computePortfolioTotals([
      account([holding({ market_value_gbp: 100, cost_basis_gbp: 80, gain_gbp: 20 })]),
    ]);
    render(<PortfolioSummary totals={totals} />);
    expect(screen.getByText("£20.00")).toBeInTheDocument();
    expect(screen.queryByText(/no reliable cost basis/i)).not.toBeInTheDocument();
  });

  it("shows an honest partial note instead of a silent £0.00 when some holdings' cost basis is unknown", () => {
    const totals = computePortfolioTotals([
      account([
        holding({ ticker: "AAA.L", market_value_gbp: 100, cost_basis_gbp: 80, gain_gbp: 20 }),
        holding({
          ticker: "ZZZ.L",
          market_value_gbp: 500,
          cost_basis_gbp: 0,
          effective_cost_basis_gbp: 500,
          gain_gbp: 0,
          gain_pct: 0,
          cost_basis_source: "unknown",
        }),
      ]),
    ]);
    render(<PortfolioSummary totals={totals} />);
    // The (real) £20 gain from the known holding must still be shown, not a
    // silent £0.00 diluted by the unknown holding's fabricated zero.
    expect(screen.getByText("£20.00")).toBeInTheDocument();
    expect(
      screen.getByText("Excludes 1 of 2 holdings with no reliable cost basis"),
    ).toBeInTheDocument();
  });

  it("states gain is unavailable, not £0.00, when no holding has a known cost basis", () => {
    const totals = computePortfolioTotals([
      account([
        holding({
          ticker: "ZZZ.L",
          market_value_gbp: 500,
          cost_basis_gbp: 0,
          effective_cost_basis_gbp: 500,
          gain_gbp: 0,
          gain_pct: 0,
          cost_basis_source: "unknown",
        }),
      ]),
    ]);
    render(<PortfolioSummary totals={totals} />);
    // This is the regression #7220 exists to fix: the Gain/loss card must
    // NEVER render as a confident "£0.00 (0.00%)" -- that is
    // indistinguishable from "you broke even" when the truth is "we don't
    // know". (£0.00 legitimately appears elsewhere -- Total cash, since
    // there's no cash holding -- so scope this to the Gain/loss card.)
    const gainLoss = screen.getByText("Gain/loss").parentElement!;
    expect(gainLoss).not.toHaveTextContent("£0.00");
    expect(gainLoss).not.toHaveTextContent("(0.00%)");
    expect(gainLoss).toHaveTextContent("—");
    expect(
      screen.getByText("Gain unavailable for all 1 holdings (no reliable cost basis)"),
    ).toBeInTheDocument();
  });

  it("shows gain from priced holdings only, with a note, when some holdings are unpriced (#8607)", () => {
    const totals = computePortfolioTotals([
      account([
        holding({ ticker: "AAA.L", market_value_gbp: 100, cost_basis_gbp: 80, gain_gbp: 20 }),
        holding({
          ticker: "NOPRICE.L",
          market_value_gbp: null,
          cost_basis_gbp: 1000,
          gain_gbp: null,
          gain_pct: null,
        }),
      ]),
    ]);
    render(<PortfolioSummary totals={totals} />);
    const gainLoss = screen.getByText("Gain/loss").parentElement!;
    expect(gainLoss).toHaveTextContent("£20.00");
    expect(gainLoss).not.toHaveTextContent("-100");
    expect(screen.getByText("Excludes 1 of 2 holdings with no price")).toBeInTheDocument();
  });

  it("shows — instead of -100% when every holding is unpriced (#8607)", () => {
    const totals = computePortfolioTotals([
      account([
        holding({
          ticker: "NOPRICE.L",
          market_value_gbp: null,
          cost_basis_gbp: 1000,
          gain_gbp: null,
          gain_pct: null,
        }),
      ]),
    ]);
    render(<PortfolioSummary totals={totals} />);
    const gainLoss = screen.getByText("Gain/loss").parentElement!;
    expect(gainLoss).toHaveTextContent("—");
    expect(gainLoss).not.toHaveTextContent("-100");
    expect(screen.getByText("Gain unavailable for all 1 holdings (no price)")).toBeInTheDocument();
  });

  it("combines cost-basis and no-price exclusions in one note (#8607)", () => {
    const totals = computePortfolioTotals([
      account([
        holding({ ticker: "AAA.L", market_value_gbp: 100, cost_basis_gbp: 80, gain_gbp: 20 }),
        holding({ ticker: "ZZZ.L", market_value_gbp: 500, cost_basis_source: "unknown" }),
        holding({ ticker: "NOPRICE.L", market_value_gbp: null, gain_gbp: null }),
      ]),
    ]);
    render(<PortfolioSummary totals={totals} />);
    expect(
      screen.getByText(
        "Excludes 1 of 3 holdings with no reliable cost basis and 1 with no price",
      ),
    ).toBeInTheDocument();
  });
});
