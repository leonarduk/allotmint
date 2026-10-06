import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, type Mock, beforeEach } from "vitest";
import { useState } from "react";
import i18n from "@/i18n";
import { configContext, type AppConfig } from "@/ConfigContext";

const defaultConfig: AppConfig = {
  relativeViewEnabled: false,
  theme: "system",
  reportingCurrency: "GBP",
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

vi.mock("@/api", () => ({
  getInstrumentDetail: vi.fn(),
  getInstrumentIntraday: vi.fn(),
  getInstrumentFxSplit: vi.fn(() => Promise.resolve({ applicable: false })),
  getTransactions: vi.fn(),
}));
import { getInstrumentDetail, getInstrumentIntraday, getTransactions } from "@/api";

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

import { InstrumentDetail } from "@/components/InstrumentDetail";

describe("InstrumentDetail", () => {
  const mockGetInstrumentDetail = getInstrumentDetail as unknown as Mock;
  const mockGetInstrumentIntraday = getInstrumentIntraday as unknown as Mock;
  const mockGetTransactions = getTransactions as unknown as Mock;

  const TestProvider = ({ children }: { children: React.ReactNode }) => {
    const [relativeViewEnabled, setRelativeViewEnabled] = useState(false);
    return (
      <configContext.Provider
        value={{
          ...defaultConfig,
          relativeViewEnabled,
          setRelativeViewEnabled,
          refreshConfig: async () => {},
        }}
      >
        <MemoryRouter>{children}</MemoryRouter>
      </configContext.Provider>
    );
  };

  const renderWithConfig = (ui: React.ReactElement) => render(<TestProvider>{ui}</TestProvider>);

  beforeEach(() => {
    mockGetInstrumentDetail.mockReset();
    mockGetInstrumentIntraday.mockReset();
    mockGetTransactions.mockReset();
    mockGetTransactions.mockResolvedValue([]);
  });

  it("renders the drawer above page content", async () => {
    mockGetInstrumentDetail.mockResolvedValue({ prices: [], positions: [], currency: null });
    mockGetInstrumentIntraday.mockResolvedValue([]);

    render(
      <MemoryRouter>
        <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />
      </MemoryRouter>,
    );

    const separator = await screen.findByRole("separator", {
      name: "Resize instrument details",
    });
    expect(separator.parentElement).toHaveStyle({ zIndex: "1000", background: "#111" });
  });

  it("links from the drawer to the full research page", async () => {
    mockGetInstrumentDetail.mockResolvedValue({ prices: [], positions: [], currency: null });
    mockGetInstrumentIntraday.mockResolvedValue([]);

    const { rerender } = render(
      <MemoryRouter>
        <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "View full page" })).toHaveAttribute(
      "href",
      "/research/ABC.L",
    );

    rerender(
      <MemoryRouter>
        <InstrumentDetail ticker="ABC.L" name="ABC" variant="standalone" />
      </MemoryRouter>,
    );

    expect(screen.queryByRole("link", { name: "View full page" })).not.toBeInTheDocument();
  });

  it("shows accessible loading skeletons before the instrument detail resolves", async () => {
    let resolveDetail: (value: { prices: unknown[]; positions: unknown[]; currency: null }) => void;
    mockGetInstrumentDetail.mockReturnValue(
      new Promise((resolve) => {
        resolveDetail = resolve;
      }),
    );

    render(
      <MemoryRouter>
        <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />
      </MemoryRouter>,
    );

    expect(screen.getAllByRole("status", { name: /loading/i }).length).toBeGreaterThan(0);

    resolveDetail!({ prices: [], positions: [], currency: null });

    await screen.findByRole("heading", { name: "ABC" });
    expect(screen.queryAllByRole("status", { name: /loading/i })).toHaveLength(0);
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
        `${i18n.t("instrumentDetail.change7d")} £30.00 (30.0%)`,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        `${i18n.t("instrumentDetail.change30d")} £30.00 (30.0%)`,
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
        `${i18n.t("instrumentDetail.change7d")} £30.00 (30.0%)`,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        `${i18n.t("instrumentDetail.change30d")} £30.00 (30.0%)`,
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

  describe("positions table (#8533)", () => {
    const fullPosition = {
      owner: "steve",
      account: "SIPP",
      units: 73,
      market_value_gbp: 876,
      unrealised_gain_gbp: 146,
      gain_gbp: 146,
      gain_pct: 20,
      cost_basis_gbp: 730,
      avg_cost_gbp: 10,
      current_price_gbp: 12,
      weight_pct: 87.6,
      acquired_date: "2024-01-02",
      days_held: 100,
      cost_basis_source: "book",
    };

    const renderPositions = async (positions: unknown[]) => {
      mockGetInstrumentDetail.mockResolvedValue({ prices: [], positions, currency: null });
      i18n.changeLanguage("en");
      renderWithConfig(<InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />);
      await screen.findByText(`${positions.length ? "steve – SIPP" : "No positions"}`);
    };

    const rowCells = (row: HTMLElement) =>
      Array.from(row.querySelectorAll("td")).map((td) => td.textContent);

    it("shows every dashboard column for a position", async () => {
      await renderPositions([fullPosition]);

      for (const header of [
        "Account",
        "Units",
        "Avg cost £",
        "Cost £",
        "Price £",
        "Mkt £",
        "Gain £",
        "Gain %",
        "Weight %",
        "Acquired",
        "Days held",
      ]) {
        expect(screen.getByRole("columnheader", { name: header })).toBeInTheDocument();
      }
      const row = screen.getByText("steve – SIPP").closest("tr")!;
      expect(rowCells(row)).toEqual([
        "steve – SIPP",
        "73.0000",
        "£10.00",
        "£730.00",
        "£12.00",
        "£876.00",
        "£146.00",
        "20.0%",
        "87.6%",
        "2024-01-02",
        "100",
      ]);
      expect(screen.queryByTestId("positions-total-row")).toBeNull();
    });

    it("keeps the % and holding-period columns in relative view", async () => {
      await renderPositions([fullPosition]);
      await userEvent.click(screen.getByLabelText("Relative view"));

      for (const hidden of ["Units", "Avg cost £", "Cost £", "Price £", "Mkt £", "Gain £"]) {
        expect(screen.queryByRole("columnheader", { name: hidden })).toBeNull();
      }
      const row = screen.getByText("steve – SIPP").closest("tr")!;
      expect(rowCells(row)).toEqual(["steve – SIPP", "20.0%", "87.6%", "2024-01-02", "100"]);
    });

    it("shows N/A with a tooltip for an unreliable cost instead of a bare dash", async () => {
      await renderPositions([
        {
          ...fullPosition,
          cost_basis_gbp: null,
          avg_cost_gbp: null,
          gain_gbp: null,
          unrealised_gain_gbp: null,
          gain_pct: null,
          acquired_date: null,
          days_held: null,
          cost_basis_source: "unknown",
        },
      ]);

      const row = screen.getByText("steve – SIPP").closest("tr")!;
      const cells = rowCells(row);
      // Avg cost, Cost, Gain £, Gain % are N/A; market value still shows.
      expect(cells.slice(2, 4)).toEqual(["N/A", "N/A"]);
      expect(cells[5]).toBe("£876.00");
      expect(cells.slice(6, 8)).toEqual(["N/A", "N/A"]);
      expect(cells).not.toContain("—");
      const na = row.querySelectorAll("td")[3].querySelector("span")!;
      expect(na).toHaveAttribute("title", i18n.t("holdingsTable.gainNotAvailable"));
    });

    it("explains a suspect booked cost in the N/A tooltip", async () => {
      await renderPositions([
        {
          ...fullPosition,
          cost_basis_gbp: null,
          avg_cost_gbp: null,
          gain_gbp: null,
          unrealised_gain_gbp: null,
          gain_pct: null,
          cost_basis_source: "book_suspect",
          cost_basis_warning: "implied_unit_cost_out_of_band",
        },
      ]);

      const row = screen.getByText("steve – SIPP").closest("tr")!;
      const cells = row.querySelectorAll("td");
      // Avg cost, Cost, Gain £, Gain % all carry the book-suspect explanation.
      for (const idx of [2, 3, 6, 7]) {
        const na = cells[idx].querySelector("span")!;
        expect(na).toHaveTextContent("N/A");
        expect(na).toHaveAttribute("title", i18n.t("holdingsTable.bookCostSuspect"));
      }
    });

    it("adds a total row when the instrument is held in several accounts", async () => {
      await renderPositions([
        fullPosition,
        {
          ...fullPosition,
          account: "ISA",
          units: 27,
          market_value_gbp: 324,
          gain_gbp: 54,
          unrealised_gain_gbp: 54,
          gain_pct: 20,
          cost_basis_gbp: 270,
          avg_cost_gbp: 10,
          weight_pct: 2.4,
        },
      ]);

      const total = screen.getByTestId("positions-total-row");
      expect(rowCells(total)).toEqual([
        "Total",
        "100.0000",
        "£10.00",
        "£1,000.00",
        "",
        "£1,200.00",
        "£200.00",
        "20.0%",
        "90.0%",
        "",
        "",
      ]);
    });

    it("withholds total cost and gain when any position's cost is unreliable", async () => {
      await renderPositions([
        fullPosition,
        {
          ...fullPosition,
          owner: "alex",
          account: "ISA",
          cost_basis_gbp: null,
          avg_cost_gbp: null,
          gain_gbp: null,
          unrealised_gain_gbp: null,
          gain_pct: null,
          cost_basis_source: "book_suspect",
        },
      ]);

      const cells = rowCells(screen.getByTestId("positions-total-row"));
      expect(cells.slice(2, 4)).toEqual(["N/A", "N/A"]);
      expect(cells[5]).toBe("£1,752.00");
      expect(cells.slice(6, 8)).toEqual(["N/A", "N/A"]);
      // Weights are shares of different owners' portfolios: not summed.
      expect(cells[8]).toBe("—");
    });
  });

  it("prefers page currency and renders native GBX prices", async () => {
    mockGetInstrumentDetail.mockResolvedValue({
      prices: [
        { date: "2024-01-01", close: 245, close_gbp: 2.45 },
        { date: "2024-01-02", close: 250, close_gbp: 2.5 },
      ],
      positions: [],
      currency: "GBP",
    });

    render(
      <MemoryRouter>
        <InstrumentDetail ticker="ABC.L" name="ABC" currency="GBX" onClose={() => {}} />
      </MemoryRouter>,
    );

    expect(await screen.findByText("250.00 GBX")).toBeInTheDocument();
    expect(screen.queryByText("£2.50")).not.toBeInTheDocument();
  });

  it("falls back to close_gbp when the native close field is absent", async () => {
    mockGetInstrumentDetail.mockResolvedValue({
      prices: [
        { date: "2024-01-01", close_gbp: 2.45 },
        { date: "2024-01-02", close_gbp: 2.5 },
      ],
      positions: [],
      currency: "GBP",
    });

    render(
      <MemoryRouter>
        <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />
      </MemoryRouter>,
    );

    // The most recent price row should render the close_gbp value in GBP,
    // exercising the `reportingClose ?? nativeClose` fallback chain.
    expect(await screen.findByText("£2.50")).toBeInTheDocument();
    expect(screen.queryByText("2.50 GBX")).not.toBeInTheDocument();
  });
  describe("trade markers overlay", () => {
    const withPrices = {
      prices: [
        { date: "2024-01-01", close: 245, close_gbp: 2.45 },
        { date: "2024-01-02", close: 250, close_gbp: 2.5 },
      ],
      positions: [],
      currency: "GBP",
    };

    it("offers the overlay unticked, alongside the other chart overlays", async () => {
      i18n.changeLanguage("en");
      mockGetInstrumentDetail.mockResolvedValue(withPrices);

      render(
        <MemoryRouter>
          <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />
        </MemoryRouter>,
      );

      const toggle = await screen.findByLabelText("Trade markers");
      expect(toggle).not.toBeChecked();
      expect(screen.getByLabelText("Bollinger Bands")).toBeInTheDocument();
    });

    it("does not fetch trades until the overlay is switched on", async () => {
      i18n.changeLanguage("en");
      mockGetInstrumentDetail.mockResolvedValue(withPrices);

      render(
        <MemoryRouter>
          <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />
        </MemoryRouter>,
      );

      await screen.findByLabelText("Trade markers");
      expect(mockGetTransactions).not.toHaveBeenCalled();

      await userEvent.click(screen.getByLabelText("Trade markers"));

      expect(screen.getByLabelText("Trade markers")).toBeChecked();
      expect(mockGetTransactions).toHaveBeenCalled();
    });

    it("keeps the chart usable when the trade lookup fails", async () => {
      i18n.changeLanguage("en");
      mockGetInstrumentDetail.mockResolvedValue(withPrices);
      mockGetTransactions.mockRejectedValue(new Error("boom"));

      render(
        <MemoryRouter>
          <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />
        </MemoryRouter>,
      );

      await userEvent.click(await screen.findByLabelText("Trade markers"));

      expect(await screen.findByRole("heading", { name: "ABC" })).toBeInTheDocument();
      expect(screen.getByLabelText("Trade markers")).toBeChecked();
    });

    it("resets the overlay when the drawer switches instrument", async () => {
      i18n.changeLanguage("en");
      mockGetInstrumentDetail.mockResolvedValue(withPrices);

      const { rerender } = render(
        <MemoryRouter>
          <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />
        </MemoryRouter>,
      );

      await userEvent.click(await screen.findByLabelText("Trade markers"));
      expect(screen.getByLabelText("Trade markers")).toBeChecked();

      rerender(
        <MemoryRouter>
          <InstrumentDetail ticker="XYZ.L" name="XYZ" onClose={() => {}} />
        </MemoryRouter>,
      );

      expect(await screen.findByLabelText("Trade markers")).not.toBeChecked();
    });

    it.each(["en", "fr", "de", "es", "pt", "it"])(
      "labels the overlay in %s",
      async (lang) => {
        mockGetInstrumentDetail.mockResolvedValue(withPrices);
        i18n.changeLanguage(lang);

        render(
          <MemoryRouter>
            <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />
          </MemoryRouter>,
        );

        const label = i18n.t("instrumentDetail.tradeMarkers");
        expect(label).not.toBe("instrumentDetail.tradeMarkers");
        expect(await screen.findByLabelText(label)).toBeInTheDocument();
      },
    );
  });
});
