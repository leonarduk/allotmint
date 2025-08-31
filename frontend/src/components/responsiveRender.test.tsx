import { render } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import "../i18n";
import { PortfolioView } from "./PortfolioView";
import { AccountBlock } from "./AccountBlock";
import { HoldingsTable } from "./HoldingsTable";
import { configContext, type AppConfig } from "../ConfigContext";
import type { Portfolio, Account, Holding } from "../types";

vi.mock("./ValueAtRisk", () => ({
  ValueAtRisk: () => <div />,
}));
vi.mock("../api", () => ({
  getInstrumentDetail: vi.fn(() => Promise.resolve({ mini: { 7: [], 30: [], 180: [] } })),
}));

const defaultConfig: AppConfig = {
  relativeViewEnabled: false,
  theme: "system",
  tabs: {
    group: true,
    owner: true,
    instrument: true,
    performance: true,
    transactions: true,
    screener: true,
    timeseries: true,
    watchlist: true,
    movers: true,
    dataadmin: true,
    virtual: true,
    reports: true,
    support: true,
    scenario: true,
    reports: true,
  },
};

const holdings: Holding[] = [
  {
    ticker: "AAA",
    name: "Alpha",
    currency: "GBP",
    instrument_type: "Equity",
    units: 5,
    price: 0,
    cost_basis_gbp: 100,
    market_value_gbp: 150,
    gain_gbp: 50,
    current_price_gbp: 30,
    latest_source: "Feed",
    acquired_date: "2024-01-01",
    days_held: 100,
    sell_eligible: true,
    days_until_eligible: 0,
  },
];

const account: Account = {
  account_type: "ISA",
  currency: "GBP",
  value_estimate_gbp: 150,
  holdings,
  last_updated: "2024-01-01",
};

const portfolio: Portfolio = {
  owner: "Alice",
  as_of: "2024-01-02",
  accounts: [account],
};

const renderWithConfig = (ui: React.ReactElement) =>
  render(
    <configContext.Provider value={{ ...defaultConfig, refreshConfig: async () => {} }}>
      {ui}
    </configContext.Provider>,
  );

describe("mobile viewport rendering", () => {
  beforeEach(() => {
    window.innerWidth = 375;
    window.dispatchEvent(new Event("resize"));
  });

  it("renders PortfolioView", () => {
    const { container } = renderWithConfig(<PortfolioView data={portfolio} />);
    expect(container.querySelector("h1")).toHaveClass("mt-0");
  });

  it("renders AccountBlock", () => {
    const { container } = renderWithConfig(<AccountBlock account={account} />);
    expect(container.firstChild).toHaveClass("mb-8", "p-4");
  });

  it("renders HoldingsTable", () => {
    const { container } = renderWithConfig(<HoldingsTable holdings={holdings} />);
    expect(container.querySelector("table")).toHaveClass("mb-4");
  });
});
