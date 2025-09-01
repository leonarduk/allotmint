import { render, act, waitFor } from "@testing-library/react";
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
    trading: true,
    screener: true,
    timeseries: true,
    watchlist: true,
    movers: true,
    dataadmin: true,
    virtual: true,
    support: true,
    settings: true,
    reports: true,
    scenario: true,
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
  trades_this_month: 0,
  trades_remaining: 0,
  total_value_estimate_gbp: 150,
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
    (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
    window.innerWidth = 375;
    window.dispatchEvent(new Event("resize"));
  });

  it("renders PortfolioView", async () => {
    let container: HTMLElement;
    await act(async () => {
      ({ container } = renderWithConfig(<PortfolioView data={portfolio} />));
    });
    await waitFor(() =>
      expect(container.querySelector("h1")).toHaveClass("mt-0"),
    );
  });

    it("renders AccountBlock", async () => {
      let container: HTMLElement;
      await act(async () => {
        ({ container } = renderWithConfig(<AccountBlock account={account} />));
      });
      await waitFor(() =>
        expect(container.firstChild).toHaveClass(
          "mb-4",
          "p-2",
          "md:mb-8",
          "md:p-4",
        ),
      );
    });

    it("renders HoldingsTable", async () => {
      let container: HTMLElement;
      await act(async () => {
        ({ container } = renderWithConfig(<HoldingsTable holdings={holdings} />));
      });
      const wrapper = container.querySelector("div.overflow-x-auto");
      await waitFor(() => expect(wrapper).toHaveClass("overflow-x-auto"));
      expect(container.querySelector("table")).toHaveClass("mb-4");
    });
  });
