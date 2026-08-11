import { render, act, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import "@/i18n";
import { AccountBlock } from "@/components/AccountBlock";
import { HoldingsTable } from "@/components/HoldingsTable";
import { configContext, type AppConfig } from "@/ConfigContext";
import type { Account, Holding } from "@/types";
import tableStyles from "@/styles/table.module.css";

vi.mock("@/components/ValueAtRisk", () => ({
  ValueAtRisk: () => <div />,
}));
vi.mock("@/api", () => ({
  getInstrumentDetail: vi.fn(() => Promise.resolve({ mini: { 7: [], 30: [], 180: [] } })),
  complianceForOwner: vi.fn().mockResolvedValue({ warnings: [] }),
  getOwnerSectorContributions: vi.fn().mockResolvedValue([]),
}));

const defaultConfig: AppConfig = {
  relativeViewEnabled: false,
  theme: "system",
  baseCurrency: "GBP",
  tabs: {
    group: true,
    market: true,
    owner: true,
    instrument: true,
    performance: true,
    transactions: true,
    trading: true,
    screener: true,
    timeseries: true,
    watchlist: true,
    allocation: true,
    rebalance: true,
    movers: true,
    instrumentadmin: true,
    dataadmin: true,
    virtual: true,
    support: true,
    settings: true,
    pension: true,
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

const renderWithConfig = (ui: React.ReactElement) =>
  render(
    <configContext.Provider
      value={{
        ...defaultConfig,
        refreshConfig: async () => {},
        setRelativeViewEnabled: () => {},
        setBaseCurrency: () => {},
      }}
    >
      {ui}
    </configContext.Provider>,
  );

describe("mobile viewport rendering", () => {
  beforeEach(() => {
    (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
    window.innerWidth = 375;
    window.dispatchEvent(new Event("resize"));
  });

    it("renders AccountBlock", async () => {
      let container!: HTMLElement;
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
      let container!: HTMLElement;
      await act(async () => {
        ({ container } = renderWithConfig(<HoldingsTable holdings={holdings} />));
      });
      const wrapper = container.querySelector(`div.${tableStyles.scrollContainer}`);
      await waitFor(() => expect(wrapper).toHaveClass(tableStyles.scrollContainer));
      expect(container.querySelector("table")).toHaveClass("mb-4");
    });
  });
