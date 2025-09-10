import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, type Mock, beforeEach } from "vitest";
import { useState } from "react";
import i18n from "../i18n";
import { configContext, type AppConfig } from "../ConfigContext";

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
    profile: true,
    pension: true,
    reports: true,
    scenario: true,
    logs: true,
  },
};

vi.mock("../api", () => ({ getInstrumentDetail: vi.fn() }));
import { getInstrumentDetail } from "../api";

class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

declare global {
  interface Window {
    ResizeObserver: typeof ResizeObserver;
  }
}


globalThis.ResizeObserver = ResizeObserver;

import { InstrumentDetail } from "./InstrumentDetail";

describe("InstrumentDetail", () => {
  const mockGetInstrumentDetail = getInstrumentDetail as unknown as Mock;

  const TestProvider = ({ children }: { children: React.ReactNode }) => {
    const [relativeViewEnabled, setRelativeViewEnabled] = useState(false);
    return (
      <configContext.Provider
        value={{
          ...defaultConfig,
          relativeViewEnabled,
          setRelativeViewEnabled,
          refreshConfig: async () => {},
          setBaseCurrency: () => {},
        }}
      >
        <MemoryRouter>{children}</MemoryRouter>
      </configContext.Provider>
    );
  };

  const renderWithConfig = (ui: React.ReactElement) => render(<TestProvider>{ui}</TestProvider>);

  beforeEach(() => {
    mockGetInstrumentDetail.mockReset();
  });

  it("shows signal action and reason when provided", async () => {
    mockGetInstrumentDetail.mockResolvedValue({
      prices: [],
      positions: [],
      currency: null,
    });

    render(
      <MemoryRouter>
        <InstrumentDetail
          ticker="ABC.L"
          name="ABC"
          signal={{
            ticker: "ABC.L",
            name: "ABC",
            action: "buy",
            reason: "test reason",
          }}
          onClose={() => {}}
        />
      </MemoryRouter>,
    );

    expect(await screen.findByText("BUY")).toBeInTheDocument();
    expect(screen.getByText(/test reason/)).toBeInTheDocument();
  });

  it.each(["en", "fr", "de", "es", "pt", "it"]) (
    "links to timeseries edit page (%s)",
    async (lang) => {
      mockGetInstrumentDetail.mockResolvedValue({
        prices: [],
        positions: [],
        currency: null,
      });

      i18n.changeLanguage(lang);

      render(
        <MemoryRouter>
          <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />
        </MemoryRouter>,
      );
      const link = await screen.findByRole("link", {
        name: i18n.t("instrumentDetail.edit"),
      });
      expect(link).toHaveAttribute("href", "/timeseries?ticker=ABC&exchange=L");
      expect(screen.getByRole("heading", { name: "ABC" })).toBeInTheDocument();
      expect(screen.getByText(/ABC\.L/)).toBeInTheDocument();
    },
  );

  it("displays 7d and 30d changes", async () => {
    const prices = Array.from({ length: 30 }, (_, i) => ({
      date: `2024-01-${String(i + 1).padStart(2, "0")}`,
      close_gbp: 100,
    }));
    prices.push({ date: "2024-01-31", close_gbp: 130 });

    mockGetInstrumentDetail.mockResolvedValue({
      prices,
      positions: [],
      currency: null,
    });

    i18n.changeLanguage("en");

    render(
      <MemoryRouter>
        <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(
        `${i18n.t("instrumentDetail.change7d")} 30.0%`,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        `${i18n.t("instrumentDetail.change30d")} 30.0%`,
      ),
    ).toBeInTheDocument();
  });

  it("uses close when close_gbp missing", async () => {
    const prices = Array.from({ length: 30 }, (_, i) => ({
      date: `2024-01-${String(i + 1).padStart(2, "0")}`,
      close: 100,
    }));
    prices.push({ date: "2024-01-31", close: 130 });

    mockGetInstrumentDetail.mockResolvedValue({
      prices,
      positions: [],
      currency: null,
    });

    i18n.changeLanguage("en");

    render(
      <MemoryRouter>
        <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(
        `${i18n.t("instrumentDetail.change7d")} 30.0%`,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        `${i18n.t("instrumentDetail.change30d")} 30.0%`,
      ),
    ).toBeInTheDocument();
  });

  it("toggles relative view", async () => {
    mockGetInstrumentDetail.mockResolvedValue({
      prices: [],
      positions: [
        {
          owner: "Alice",
          account: "Acct",
          units: 1,
          market_value_gbp: 100,
          unrealised_gain_gbp: 10,
          gain_pct: 10,
        },
      ],
      currency: null,
    });

    i18n.changeLanguage("en");

    renderWithConfig(
      <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />,
    );

    await screen.findByText("Alice – Acct");
    const toggle = screen.getByLabelText('Relative view');
    await userEvent.click(toggle);

    expect(screen.queryByRole('columnheader', { name: /Units/ })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: /Mkt £/ })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: /Gain £/ })).toBeNull();
    expect(screen.getByRole('columnheader', { name: /Gain %/ })).toBeInTheDocument();
  });
});

