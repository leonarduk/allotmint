import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { createInstance } from "i18next";
import type { ReactElement } from "react";
import en from "../locales/en/translation.json";
import fr from "../locales/fr/translation.json";

vi.mock("../api", () => ({
  API_BASE: "http://api",
  getOwners: vi.fn().mockResolvedValue([
    { owner: "Alice", accounts: [] },
    { owner: "Bob", accounts: [] },
  ]),
  runCustomQuery: vi.fn().mockResolvedValue([
    { owner: "Alice", ticker: "AAA", market_value_gbp: 100 },
  ]),
  saveCustomQuery: vi.fn().mockResolvedValue({}),
  listSavedQueries: vi.fn().mockResolvedValue([
    {
      id: "1",
      name: "Saved1",
      params: {
        start: "2024-01-01",
        end: "2024-01-31",
        owners: ["Bob"],
        tickers: ["BBB"],
        metrics: ["market_value_gbp"],
      },
    },
  ]),
  getScreener: vi.fn().mockResolvedValue([
    {
      ticker: "AAA",
      name: "Alpha",
      peg_ratio: 1,
      pe_ratio: 10,
      de_ratio: 0.5,
      fcf: 1000,
      eps: 2,
      gross_margin: 0.4,
      operating_margin: 0.2,
      net_margin: 0.1,
      ebitda_margin: 0.3,
      roa: 0.1,
      roe: 0.2,
      roi: 0.15,
      dividend_yield: 2,
      dividend_payout_ratio: 40,
      beta: 1.2,
      shares_outstanding: 1000,
      float_shares: 800,
      market_cap: 5000,
      high_52w: 150,
      low_52w: 90,
      avg_volume: 2000,
    },
  ]),
}));

import { getScreener, runCustomQuery } from "../api";
import { ScreenerQuery } from "./ScreenerQuery";

function renderWithI18n(ui: ReactElement) {
  const i18n = createInstance();
  i18n.use(initReactI18next).init({
    lng: "en",
    resources: { en: { translation: en }, fr: { translation: fr } },
  });
  const result = render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
  return { i18n, ...result };
}

describe("Screener & Query page", () => {
  it("runs screener and displays results", async () => {
    renderWithI18n(<ScreenerQuery />);

    fireEvent.change(screen.getByLabelText(en.screener.tickers), {
      target: { value: "AAA" },
    });
    fireEvent.change(screen.getByLabelText(en.screener.maxPeg), {
      target: { value: "2" },
    });
    fireEvent.change(screen.getByLabelText(en.screener.minRoe), {
      target: { value: "5" },
    });

    fireEvent.click(screen.getAllByRole("button", { name: en.screener.run })[0]);

    expect((await screen.findAllByText("1,000")).length).toBeGreaterThan(0);
    expect(getScreener).toHaveBeenNthCalledWith(
      1,
      ["AAA"],
      expect.objectContaining({ peg_max: 2, roe_min: 5 })
    );

    fireEvent.change(screen.getByLabelText(en.screener.minDividendYield), {
      target: { value: "1" },
    });
    fireEvent.click(screen.getAllByRole("button", { name: en.screener.run })[0]);

    expect(await screen.findByText("1.2")).toBeInTheDocument();
    expect(getScreener).toHaveBeenNthCalledWith(
      2,
      ["AAA"],
      expect.objectContaining({ peg_max: 2, dividend_yield_min: 1 })
    );
  });

  it("submits query form and renders results with export links", async () => {
    const { i18n } = renderWithI18n(<ScreenerQuery />);

    await screen.findByLabelText("Alice");

    fireEvent.change(screen.getByLabelText(i18n.t("query.start")), {
      target: { value: "2024-01-01" },
    });
    fireEvent.change(screen.getByLabelText(i18n.t("query.end")), {
      target: { value: "2024-02-01" },
    });

    fireEvent.click(screen.getByLabelText("Alice"));
    fireEvent.click(screen.getByLabelText("AAA"));
    fireEvent.click(screen.getByLabelText("market_value_gbp"));

    fireEvent.click(screen.getAllByRole("button", { name: i18n.t("query.run") })[1]);

    expect(runCustomQuery).toHaveBeenCalledWith({
      start: "2024-01-01",
      end: "2024-02-01",
      owners: ["Alice"],
      tickers: ["AAA"],
      metrics: ["market_value_gbp"],
    });

    expect(await screen.findByText("AAA")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /csv/i })).toHaveAttribute(
      "href",
      expect.stringContaining("format=csv"),
    );
    expect(screen.getByRole("link", { name: /xlsx/i })).toHaveAttribute(
      "href",
      expect.stringContaining("format=xlsx"),
    );
  });

  it("loads saved queries into the form", async () => {
    const { i18n } = renderWithI18n(<ScreenerQuery />);
    const btn = await screen.findByText("Saved1");
    fireEvent.click(btn);
    expect(screen.getByLabelText(i18n.t("query.start"))).toHaveValue("2024-01-01");
  });

  it("switches labels when language changes", async () => {
    const { i18n, rerender } = renderWithI18n(<ScreenerQuery />);
    await screen.findByLabelText(i18n.t("query.start"));
    await act(async () => {
      await i18n.changeLanguage("fr");
    });
    rerender(
      <I18nextProvider i18n={i18n}>
        <ScreenerQuery />
      </I18nextProvider>,
    );
    expect(
      await screen.findByLabelText(i18n.t("query.start")),
    ).toBeInTheDocument();
  });
});
