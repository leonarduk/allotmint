import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { GroupPortfolioView } from "./GroupPortfolioView";
import i18n from "../i18n";

afterEach(() => {
  vi.restoreAllMocks();
  i18n.changeLanguage("en");
});

describe("GroupPortfolioView", () => {
  it("shows per-owner totals with percentages", async () => {
    const mockPortfolio = {
      name: "All owners combined",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 100,
          holdings: [
            {
              units: 1,
              cost_basis_gbp: 80,
              market_value_gbp: 100,
              day_change_gbp: 5,
            },
          ],
        },
        {
          owner: "bob",
          account_type: "isa",
          value_estimate_gbp: 200,
          holdings: [
            {
              units: 1,
              cost_basis_gbp: 150,
              market_value_gbp: 200,
              day_change_gbp: -10,
            },
          ],
        },
      ],
    };

    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => mockPortfolio,
    } as unknown as Response);

    render(<GroupPortfolioView slug="all" />);

    await waitFor(() => screen.getByText("alice"));

    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.getByText("bob")).toBeInTheDocument();
    expect(screen.getByText("25.00%"))
      .toBeInTheDocument();
    expect(screen.getByText("-4.76%"))
      .toBeInTheDocument();
  });

  it("renders instrument type pie chart", async () => {
    const mockPortfolio = {
      name: "All owners combined",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 100,
          holdings: [
            {
              units: 1,
              cost_basis_gbp: 80,
              market_value_gbp: 100,
              instrument_type: "equity",
            },
          ],
        },
        {
          owner: "bob",
          account_type: "isa",
          value_estimate_gbp: 200,
          holdings: [
            {
              units: 1,
              cost_basis_gbp: 200,
              market_value_gbp: 200,
              instrument_type: "cash",
            },
          ],
        },
      ],
    };

    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => mockPortfolio,
    } as unknown as Response);

    render(<GroupPortfolioView slug="all" />);

    await waitFor(() => screen.getAllByText("Equity"));

    expect(screen.getAllByText("Equity").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Cash").length).toBeGreaterThan(0);
  });


  const locales = ["en", "fr", "de", "es", "pt"] as const;

  it.each(locales)("renders select group message in %s", async (lng) => {
    await i18n.changeLanguage(lng);
    render(<GroupPortfolioView slug="" />);
    expect(screen.getByText(i18n.t("group.select"))).toBeInTheDocument();
  });

  it.each(locales)("renders error message in %s", async (lng) => {
    await i18n.changeLanguage(lng);
    vi.spyOn(global, "fetch").mockRejectedValueOnce(new Error("boom"));
    render(<GroupPortfolioView slug="all" />);
    await waitFor(() =>
      screen.getByText(`${i18n.t("common.error")}: boom`)
    );
  });

  it.each(locales)("renders loading message in %s", async (lng) => {
    await i18n.changeLanguage(lng);
    vi.spyOn(global, "fetch").mockImplementation(
      () => new Promise(() => {})
    );
    render(<GroupPortfolioView slug="all" />);
    expect(screen.getByText(i18n.t("common.loading"))).toBeInTheDocument();
  });

  it("updates totals when accounts are toggled", async () => {
    await i18n.changeLanguage("en");
    const mockPortfolio = {
      name: "All owners combined",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 100,
          holdings: [],
        },
        {
          owner: "bob",
          account_type: "isa",
          value_estimate_gbp: 200,
          holdings: [],
        },
      ],
    };

    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => mockPortfolio,
    } as unknown as Response);

    render(<GroupPortfolioView slug="all" />);

    await waitFor(() => screen.getByLabelText(/alice isa/i));

    const totalLabel = screen.getAllByText("Total Value")[0];
    const valueEl = totalLabel.nextElementSibling as HTMLElement;
    expect(valueEl).toHaveTextContent("£300.00");

    const bobCheckbox = screen.getByLabelText(/bob isa/i);
    fireEvent.click(bobCheckbox);

    expect(valueEl).toHaveTextContent("£100.00");
  });
});
