import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, type Mock, beforeEach } from "vitest";
import i18n from "../i18n";
import { configContext, type AppConfig } from "../ConfigContext";

const defaultConfig: AppConfig = {
  relativeViewEnabled: false,
  theme: "system",
  tabs: {
    instrument: true,
    performance: true,
    transactions: true,
    screener: true,
    timeseries: true,
    groupInstrumentMemberTimeseries: true,
    watchlist: true,
    movers: true,
    virtual: true,
    support: true,
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

  const renderWithConfig = (ui: React.ReactElement, cfg: Partial<AppConfig>) =>
    render(
      <configContext.Provider value={{ ...defaultConfig, ...cfg }}>
        <MemoryRouter>{ui}</MemoryRouter>
      </configContext.Provider>,
    );

  beforeEach(() => {
    mockGetInstrumentDetail.mockReset();
  });

  it.each(["en", "fr", "de", "es", "pt"]) (
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

  it("hides absolute columns in relative view", async () => {
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
      { relativeViewEnabled: true },
    );

    await screen.findByText("Alice – Acct");

    expect(screen.queryByRole('columnheader', { name: /Units/ })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: /Mkt £/ })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: /Gain £/ })).toBeNull();
    expect(screen.getByRole('columnheader', { name: /Gain %/ })).toBeInTheDocument();
  });

  it("shows absolute columns when relative view disabled", async () => {
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
      { relativeViewEnabled: false },
    );

    await screen.findByText("Alice – Acct");

    expect(screen.getByRole('columnheader', { name: /Units/ })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Mkt £/ })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Gain £/ })).toBeInTheDocument();
  });
});

