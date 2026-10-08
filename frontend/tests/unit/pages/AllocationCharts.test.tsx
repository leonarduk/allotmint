import type { ReactNode } from "react";
import { fireEvent, render as rtlRender, screen, within, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import AllocationCharts from "@/pages/AllocationCharts";
import * as api from "@/api";
import type { GroupPortfolio, Holding, LookThroughExposure } from "@/types";
import { MemoryRouter } from "react-router-dom";
import { configContext, useConfig } from "@/ConfigContext";

const chartFormatters = vi.hoisted(() => ({
  legend: null as null | ((value: string, entry: unknown) => string),
  tooltip: null as null | ((value: unknown, name: unknown, item: unknown) => string),
}));

vi.mock("@/api");
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  PieChart: ({ children }: { children: ReactNode }) => (
    <div data-testid="pie-chart">{children}</div>
  ),
  Pie: ({ data, children, label }: { data: Array<{ name: string; value: number }>; children: ReactNode; label?: unknown }) => (
    <div data-testid="pie-slices" data-inline-labels={Boolean(label)}>
      {data.length === 0 ? (
        <span data-testid="no-slices">no-slices</span>
      ) : (
        data.map((slice) => (
          <span key={slice.name} data-testid="slice-row">{`${slice.name}: ${slice.value}`}</span>
        ))
      )}
      {children}
    </div>
  ),
  Cell: () => null,
  Tooltip: ({ formatter }: { formatter: typeof chartFormatters.tooltip }) => {
    chartFormatters.tooltip = formatter;
    return null;
  },
  Legend: ({ formatter }: { formatter: typeof chartFormatters.legend }) => {
    chartFormatters.legend = formatter;
    return null;
  },
}));

const mockGetGroupPortfolio = vi.mocked(api.getGroupPortfolio);
const mockGetGroupCurrencies = vi.mocked(api.getGroupCurrencyContributions);
const mockGetGroupLookThrough = vi.mocked(api.getGroupLookThrough);
const mockGetOwnerCurrencies = vi.mocked(api.getOwnerCurrencyContributions);
const mockGetOwnerLookThrough = vi.mocked(api.getOwnerLookThrough);

const render = (ui: ReactNode, initialEntry = "/allocation") =>
  rtlRender(<MemoryRouter initialEntries={[initialEntry]}>{ui}</MemoryRouter>);

const baseHolding: Holding = {
  ticker: "AAA",
  name: "Alpha",
  units: 1,
  acquired_date: "2024-01-01",
  market_value_gbp: 100,
  instrument_type: "equity",
  sector: "Tech",
  region: "UK",
};

const samplePortfolio: GroupPortfolio = {
  slug: "g",
  name: "Group",
  as_of: "2024-01-01",
  members: [],
  total_value_estimate_gbp: 100,
  trades_this_month: 0,
  trades_remaining: 0,
  accounts: [
    {
      account_type: "taxable",
      currency: "GBP",
      value_estimate_gbp: 100,
      owner: "alice",
      holdings: [baseHolding],
    },
  ],
  members_summary: [],
  subtotals_by_account_type: {},
};

const buildPortfolio = (holdings: Holding[]): GroupPortfolio => ({
  ...samplePortfolio,
  accounts: [{ ...samplePortfolio.accounts[0], holdings }],
});

describe("AllocationCharts page", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
    vi.stubEnv("MODE", "development");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("shows loading indicator while fetching", async () => {
    let resolveFn: (p: GroupPortfolio) => void;
    const promise = new Promise<GroupPortfolio>((resolve) => {
      resolveFn = resolve;
    });
    mockGetGroupPortfolio.mockReturnValueOnce(promise);

    render(<AllocationCharts />);
    expect(screen.getByRole("status", { name: /Loading/ })).toBeInTheDocument();

    resolveFn!(samplePortfolio);
    expect(await screen.findByText(/Instrument Types/)).toBeInTheDocument();
    expect(screen.queryByRole("status", { name: /Loading/ })).not.toBeInTheDocument();
  });

  it("uses the legend instead of inline labels on mobile viewports", async () => {
    mockGetGroupPortfolio.mockResolvedValueOnce(samplePortfolio);
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 375 });

    render(<AllocationCharts />);

    expect(await screen.findByTestId("pie-slices")).toHaveAttribute(
      "data-inline-labels",
      "false",
    );
  });

  it("restores inline labels when the viewport grows", async () => {
    mockGetGroupPortfolio.mockResolvedValueOnce(samplePortfolio);
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 375 });
    render(<AllocationCharts />);
    const pie = await screen.findByTestId("pie-slices");

    Object.defineProperty(window, "innerWidth", { configurable: true, value: 800 });
    fireEvent(window, new Event("resize"));

    expect(pie).toHaveAttribute("data-inline-labels", "true");
  });

  it("displays an error message when API call fails", async () => {
    mockGetGroupPortfolio.mockRejectedValueOnce(new Error("boom"));
    render(<AllocationCharts />);
    expect(await screen.findByText("boom")).toBeInTheDocument();
    expect(screen.queryByText(/Loading/)).not.toBeInTheDocument();
  });

  it("opens a linked allocation dimension for the linked group and scope", async () => {
    mockGetGroupPortfolio.mockResolvedValueOnce(samplePortfolio);

    render(<AllocationCharts />, "/allocation?group=family&view=sector&owner=alice&account=taxable");

    await waitFor(() => expect(mockGetGroupPortfolio).toHaveBeenCalledWith("family"));
    expect(screen.getByRole("button", { name: "Industries" })).toBeDisabled();
    expect(screen.getByRole("tab", { name: "alice" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "taxable" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("link", { name: "View gain contribution" })).toHaveAttribute(
      "href",
      "/?group=family&owner=alice&account=taxable",
    );
  });

  describe("owner/account filter (#10011)", () => {
    const twoOwnerPortfolio: GroupPortfolio = {
      ...samplePortfolio,
      accounts: [
        { ...samplePortfolio.accounts[0], account_type: "sipp", holdings: [baseHolding] },
        {
          ...samplePortfolio.accounts[0],
          account_type: "isa",
          holdings: [{ ...baseHolding, ticker: "BBB", market_value_gbp: 40, instrument_type: "bond" }],
        },
        {
          ...samplePortfolio.accounts[0],
          owner: "bob",
          account_type: "isa",
          holdings: [{ ...baseHolding, ticker: "CCC", market_value_gbp: 7, instrument_type: "cash" }],
        },
      ],
    };
    const sliceNames = () =>
      within(screen.getByTestId("pie-slices"))
        .getAllByTestId("slice-row")
        .map((el) => el.textContent);

    it("shows the same owner tabs as the overview, with display names", async () => {
      mockGetGroupPortfolio.mockResolvedValueOnce(twoOwnerPortfolio);
      render(
        <AllocationCharts owners={[{ owner: "alice", full_name: "Alice Smith", accounts: [] }]} />,
      );

      expect(await screen.findByRole("tab", { name: "All positions" })).toHaveAttribute(
        "aria-selected",
        "true",
      );
      expect(screen.getByRole("tab", { name: "Alice Smith" })).toBeInTheDocument();
      expect(screen.getByRole("tab", { name: "bob" })).toBeInTheDocument();
      expect(screen.queryByRole("tab", { name: "All accounts" })).not.toBeInTheDocument();
      await waitFor(() => expect(sliceNames()).toHaveLength(3));
    });

    it("narrows the charts by owner, then by account", async () => {
      mockGetGroupPortfolio.mockResolvedValueOnce(twoOwnerPortfolio);
      render(<AllocationCharts />);

      fireEvent.click(await screen.findByRole("tab", { name: "alice" }));
      await waitFor(() => expect(sliceNames()).toEqual(["Equity: 100", "Bond: 40"]));

      fireEvent.click(screen.getByRole("tab", { name: "isa" }));
      await waitFor(() => expect(sliceNames()).toEqual(["Bond: 40"]));

      fireEvent.click(screen.getByRole("tab", { name: "All positions" }));
      await waitFor(() => expect(sliceNames()).toHaveLength(3));
    });

    it("drops an owner the group does not have", async () => {
      mockGetGroupPortfolio.mockResolvedValueOnce(twoOwnerPortfolio);
      render(<AllocationCharts />, "/allocation?owner=nobody");

      await waitFor(() =>
        expect(screen.getByRole("tab", { name: "All positions" })).toHaveAttribute(
          "aria-selected",
          "true",
        ),
      );
      await waitFor(() => expect(sliceNames()).toHaveLength(3));
    });
  });

  it("keeps valid values across type/sector/region while excluding invalid entries", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    mockGetGroupPortfolio.mockResolvedValueOnce(
      buildPortfolio([
        { ...baseHolding, ticker: "NEG", market_value_gbp: -20, sector: "Utilities", region: "EU" },
        { ...baseHolding, ticker: "BAD", market_value_gbp: Number.NaN as unknown as number, sector: "Finance" },
        { ...baseHolding, ticker: "OK", market_value_gbp: 100, sector: "Tech", region: "UK" },
      ]),
    );

    render(<AllocationCharts />);

    expect(await screen.findByText(/Instrument Types/)).toBeInTheDocument();
    // asset/type dimension
    // The chart effect runs asynchronously after loading resolves — use waitFor.
    await waitFor(() => {
      expect(within(screen.getByTestId("pie-slices")).getByText("Equity: 100")).toBeInTheDocument();
    });

    // sector dimension
    fireEvent.click(screen.getByRole("button", { name: /^(industries|sectors?)$/i }));
    let slices = screen.getByTestId("pie-slices");
    expect(within(slices).getByText("Tech: 100")).toBeInTheDocument();
    expect(within(slices).queryByText(/Utilities/)).not.toBeInTheDocument();
    expect(within(slices).queryByText(/Finance/)).not.toBeInTheDocument();

    // region dimension
    fireEvent.click(screen.getByRole("button", { name: /regions|region/i }));
    slices = screen.getByTestId("pie-slices");
    expect(within(slices).getByText("UK: 100")).toBeInTheDocument();
    expect(within(slices).queryByText(/^EU:/)).not.toBeInTheDocument();

    expect(warnSpy).toHaveBeenCalledWith("Dropped invalid holding value", {
      ticker: "NEG",
      originalValue: -20,
      coercedValue: -20,
      originalInvalid: false,
      dropReason: "non-positive-market-value",
    });
  });

  it("excludes zero market values", async () => {
    mockGetGroupPortfolio.mockResolvedValueOnce(
      buildPortfolio([
        { ...baseHolding, ticker: "ZERO", market_value_gbp: 0, sector: "Zero Sector" },
        { ...baseHolding, ticker: "VALID", market_value_gbp: 50, sector: "Tech" },
      ]),
    );

    render(<AllocationCharts />);

    await screen.findByText(/Instrument Types/);
    fireEvent.click(screen.getByRole("button", { name: /^(industries|sectors?)$/i }));

    const slices = screen.getByTestId("pie-slices");
    expect(within(slices).getByText("Tech: 50")).toBeInTheDocument();
    expect(within(slices).queryByText(/Zero Sector/)).not.toBeInTheDocument();
  });

  it("excludes infinity and negative infinity values", async () => {
    mockGetGroupPortfolio.mockResolvedValueOnce(
      buildPortfolio([
        { ...baseHolding, ticker: "INF", market_value_gbp: Number.POSITIVE_INFINITY, sector: "Energy" },
        { ...baseHolding, ticker: "NINF", market_value_gbp: Number.NEGATIVE_INFINITY, sector: "Materials" },
        { ...baseHolding, ticker: "VALID", market_value_gbp: 25, sector: "Tech" },
      ]),
    );

    render(<AllocationCharts />);

    await screen.findByText(/Instrument Types/);
    fireEvent.click(screen.getByRole("button", { name: /^(industries|sectors?)$/i }));

    const slices = screen.getByTestId("pie-slices");
    expect(within(slices).getByText("Tech: 25")).toBeInTheDocument();
    expect(within(slices).queryByText(/Energy/)).not.toBeInTheDocument();
    expect(within(slices).queryByText(/Materials/)).not.toBeInTheDocument();
  });

  it("warns in dev for dropped NaN values and reports original value", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    mockGetGroupPortfolio.mockResolvedValueOnce(
      buildPortfolio([
        { ...baseHolding, ticker: "NAN", market_value_gbp: Number.NaN as unknown as number, sector: "Finance" },
        { ...baseHolding, ticker: "VALID", market_value_gbp: 10, sector: "Tech" },
      ]),
    );

    render(<AllocationCharts />);
    await screen.findByText(/Instrument Types/);

    // The chart-data useEffect emits the warning asynchronously after the
    // loading guard drops (which makes "Instrument Types" visible). Use
    // waitFor so the assertion retries until the effect has actually run.
    await waitFor(() => {
      expect(warnSpy).toHaveBeenCalledWith("Dropped invalid holding value", {
        ticker: "NAN",
        originalValue: Number.NaN,
        coercedValue: 0,
        originalInvalid: true,
        dropReason: "invalid-numeric-input",
      });
    });
  });

  it("warns in dev for dropped Infinity values", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    mockGetGroupPortfolio.mockResolvedValueOnce(
      buildPortfolio([
        { ...baseHolding, ticker: "INF", market_value_gbp: Number.POSITIVE_INFINITY, sector: "Energy" },
        { ...baseHolding, ticker: "VALID", market_value_gbp: 10, sector: "Tech" },
      ]),
    );

    render(<AllocationCharts />);
    await screen.findByText(/Instrument Types/);

    // The chart-data useEffect emits the warning asynchronously after the
    // loading guard drops (which makes "Instrument Types" visible). Use
    // waitFor so the assertion retries until the effect has actually run.
    await waitFor(() => {
      expect(warnSpy).toHaveBeenCalledWith("Dropped invalid holding value", {
        ticker: "INF",
        originalValue: Number.POSITIVE_INFINITY,
        coercedValue: 0,
        originalInvalid: true,
        dropReason: "invalid-numeric-input",
      });
    });
  });

  it("warns in dev for dropped non-numeric values", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    mockGetGroupPortfolio.mockResolvedValueOnce(
      buildPortfolio([
        {
          ...baseHolding,
          ticker: "STR",
          // Runtime API payloads can still return non-numeric data despite frontend type declarations.
          market_value_gbp: "N/A" as unknown as number,
          sector: "Unknown",
        },
      ]),
    );

    render(<AllocationCharts />);
    await screen.findByText(/Instrument Types/);

    // The chart-data useEffect emits the warning asynchronously after the
    // loading guard drops (which makes "Instrument Types" visible). Use
    // waitFor so the assertion retries until the effect has actually run.
    await waitFor(() => {
      expect(warnSpy).toHaveBeenCalledWith("Dropped invalid holding value", {
        ticker: "STR",
        originalValue: "N/A",
        coercedValue: 0,
        originalInvalid: true,
        dropReason: "invalid-numeric-input",
      });
    });
  });

  it("adds blocking coverage for null market values", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    mockGetGroupPortfolio.mockResolvedValueOnce(
      buildPortfolio([
        {
          ...baseHolding,
          ticker: "NULL",
          market_value_gbp: null as unknown as number,
          sector: "Finance",
        },
        { ...baseHolding, ticker: "VALID", market_value_gbp: 10, sector: "Tech" },
      ]),
    );

    render(<AllocationCharts />);
    await screen.findByText(/Instrument Types/);

    // The chart effect runs asynchronously after the loading state resolves.
    // Use waitFor so the pie-slices assertion is deferred until assetData is populated.
    await waitFor(() => {
      const slices = screen.getByTestId("pie-slices");
      expect(within(slices).getByText("Equity: 10")).toBeInTheDocument();
    });

    expect(warnSpy).toHaveBeenCalledWith("Dropped invalid holding value", {
      ticker: "NULL",
      originalValue: null,
      coercedValue: 0,
      originalInvalid: false,
      dropReason: "non-positive-market-value",
    });
  });

  it("adds blocking coverage for undefined market values", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    mockGetGroupPortfolio.mockResolvedValueOnce(
      buildPortfolio([
        {
          ...baseHolding,
          ticker: "UNDEF",
          market_value_gbp: undefined as unknown as number,
          sector: "Finance",
        },
        { ...baseHolding, ticker: "VALID", market_value_gbp: 12, sector: "Tech" },
      ]),
    );

    render(<AllocationCharts />);
    await screen.findByText(/Instrument Types/);

    // Same async chart-effect timing issue as the null test — use waitFor.
    await waitFor(() => {
      const slices = screen.getByTestId("pie-slices");
      expect(within(slices).getByText("Equity: 12")).toBeInTheDocument();
    });

    expect(warnSpy).toHaveBeenCalledWith("Dropped invalid holding value", {
      ticker: "UNDEF",
      originalValue: undefined,
      coercedValue: 0,
      originalInvalid: true,
      dropReason: "invalid-numeric-input",
    });
  });

  it("renders an empty chart state when all holdings are invalid", async () => {
    mockGetGroupPortfolio.mockResolvedValueOnce(
      buildPortfolio([
        { ...baseHolding, ticker: "NAN", market_value_gbp: Number.NaN as unknown as number, sector: "Finance" },
        { ...baseHolding, ticker: "NEG", market_value_gbp: -10, sector: "Utilities" },
        { ...baseHolding, ticker: "ZERO", market_value_gbp: 0, sector: "Zero" },
      ]),
    );

    render(<AllocationCharts />);

    expect(await screen.findByText(/Instrument Types/)).toBeInTheDocument();
    expect(screen.getByTestId("pie-chart")).toBeInTheDocument();
    expect(screen.getByTestId("no-slices")).toBeInTheDocument();
  });

  it("preserves aggregation sums for multiple valid holdings", async () => {
    mockGetGroupPortfolio.mockResolvedValueOnce(
      buildPortfolio([
        { ...baseHolding, ticker: "AAA", market_value_gbp: 30, sector: "Tech" },
        { ...baseHolding, ticker: "BBB", market_value_gbp: 70, sector: "Tech" },
        { ...baseHolding, ticker: "CCC", market_value_gbp: 50, sector: "Health" },
      ]),
    );

    render(<AllocationCharts />);

    await screen.findByText(/Instrument Types/);
    fireEvent.click(screen.getByRole("button", { name: /^(industries|sectors?)$/i }));

    const slices = screen.getByTestId("pie-slices");
    expect(within(slices).getByText("Tech: 100")).toBeInTheDocument();
    expect(within(slices).getByText("Health: 50")).toBeInTheDocument();
  });

  it("suppresses all dropped-value warnings in production", async () => {
    vi.stubEnv("MODE", "production");
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    mockGetGroupPortfolio.mockResolvedValueOnce(
      buildPortfolio([
        { ...baseHolding, ticker: "NEG", market_value_gbp: -1, sector: "Utilities" },
        { ...baseHolding, ticker: "NAN", market_value_gbp: Number.NaN as unknown as number, sector: "Utilities" },
        { ...baseHolding, ticker: "INF", market_value_gbp: Number.POSITIVE_INFINITY, sector: "Utilities" },
        { ...baseHolding, ticker: "STR", market_value_gbp: "N/A" as unknown as number, sector: "Utilities" },
      ]),
    );

    render(<AllocationCharts />);
    await screen.findByText(/Instrument Types/);

    expect(warnSpy).not.toHaveBeenCalled();
  });

  describe("currency view (#9686)", () => {
    const currencyRow = (quote_currency: string, market_value_gbp: number) => ({
      quote_currency,
      market_value_gbp,
      gain_gbp: 0,
      cost_gbp: market_value_gbp,
      currency: "GBP",
    });

    it("fetches quote-currency exposure only when the view is opened", async () => {
      mockGetGroupPortfolio.mockResolvedValueOnce(samplePortfolio);
      mockGetGroupCurrencies.mockResolvedValueOnce([
        currencyRow("GBP", 60),
        currencyRow("USD", 300),
        currencyRow("Unknown", 5),
        currencyRow("EUR", 0),
      ]);

      render(<AllocationCharts />);
      await screen.findByText(/Instrument Types/);
      expect(mockGetGroupCurrencies).not.toHaveBeenCalled();

      fireEvent.click(screen.getByRole("button", { name: "Currencies" }));

      await waitFor(() => expect(mockGetGroupCurrencies).toHaveBeenCalledWith("all"));
      const slices = screen.getByTestId("pie-slices");
      await waitFor(() =>
        expect(within(slices).getAllByTestId("slice-row").map((el) => el.textContent)).toEqual([
          "USD: 300",
          "GBP: 60",
          "Unknown currency: 5",
        ]),
      );
      expect(screen.getByRole("button", { name: "Currencies" })).toBeDisabled();
    });

    it("labels the view as quote-currency exposure", async () => {
      mockGetGroupPortfolio.mockResolvedValueOnce(samplePortfolio);
      mockGetGroupCurrencies.mockResolvedValueOnce([currencyRow("GBP", 100)]);

      render(<AllocationCharts />, "/allocation?group=family&view=currency");

      await waitFor(() => expect(mockGetGroupCurrencies).toHaveBeenCalledWith("family"));
      expect(await screen.findByTestId("currency-exposure-note")).toHaveTextContent(
        /quote currency.*GBP-listed global fund counts as GBP/,
      );
    });

    it("uses the owner currency endpoint when an owner is selected", async () => {
      mockGetGroupCurrencies.mockClear();
      mockGetGroupPortfolio.mockResolvedValueOnce(samplePortfolio);
      mockGetOwnerCurrencies.mockResolvedValueOnce([currencyRow("USD", 80)]);

      render(<AllocationCharts />, "/allocation?view=currency&owner=alice");

      await waitFor(() => expect(mockGetOwnerCurrencies).toHaveBeenCalledWith("alice"));
      expect(await screen.findByText("USD: 80")).toBeInTheDocument();
      expect(mockGetGroupCurrencies).not.toHaveBeenCalled();
    });

    it("warns when a quote currency has no stored FX rate", async () => {
      mockGetGroupPortfolio.mockResolvedValueOnce(samplePortfolio);
      mockGetGroupCurrencies.mockResolvedValueOnce([
        currencyRow("GBP", 100),
        {
          ...currencyRow("JPY", 20),
          unconverted_holdings: [
            { ticker: "AAA.JP", currency: "JPY", reason: "no stored FX rate" },
            { ticker: "BBB.JP", currency: "JPY", reason: "no stored FX rate" },
          ],
        },
      ]);

      render(<AllocationCharts />, "/allocation?view=currency");

      expect(await screen.findByTestId("currency-missing-fx")).toHaveTextContent(
        "No stored exchange rate for JPY (2)",
      );
    });

    it("shows no FX warning when every currency has a stored rate", async () => {
      mockGetGroupPortfolio.mockResolvedValueOnce(samplePortfolio);
      mockGetGroupCurrencies.mockResolvedValueOnce([
        { ...currencyRow("USD", 100), unconverted_holdings: [] },
      ]);

      render(<AllocationCharts />, "/allocation?view=currency");

      await waitFor(() => expect(mockGetGroupCurrencies).toHaveBeenCalled());
      expect(await screen.findByText("USD: 100")).toBeInTheDocument();
      expect(screen.queryByTestId("currency-missing-fx")).not.toBeInTheDocument();
    });

    it("shows the currency endpoint error without breaking other views", async () => {
      mockGetGroupPortfolio.mockResolvedValueOnce(samplePortfolio);
      mockGetGroupCurrencies.mockRejectedValueOnce(new Error("currency boom"));

      render(<AllocationCharts />, "/allocation?view=currency");

      expect(await screen.findByText("currency boom")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /Instrument Types/ }));
      expect(screen.queryByText("currency boom")).not.toBeInTheDocument();
      expect(screen.getByRole("tab", { name: "alice" })).toBeInTheDocument();
    });
  });

  describe("sleeve view (#9813)", () => {
    const mockGetSleeves = vi.mocked(api.getSleeves);
    const sleeves = (assignments: Record<string, string>) => ({
      sleeves: [
        { id: "core", name: "Core", size_pct: 90, targets: {}, strategy: null },
        { id: "sleeve-1", name: "Speculative", size_pct: 10, targets: { equity: 100 }, strategy: null },
      ],
      assignments,
      holdings: [],
    });

    it("groups value by each owner's sleeve tags", async () => {
      const alice = samplePortfolio.accounts[0];
      mockGetGroupPortfolio.mockResolvedValueOnce({
        ...samplePortfolio,
        accounts: [
          { ...alice, holdings: [baseHolding, { ...baseHolding, ticker: "BBB", market_value_gbp: 50 }] },
          { ...alice, owner: "bob", holdings: [{ ...baseHolding, market_value_gbp: 30 }] },
        ],
      });
      // AAA is speculative for alice only; bob's AAA stays in his core.
      mockGetSleeves.mockImplementation(async (owner: string) =>
        owner === "alice" ? sleeves({ AAA: "sleeve-1" }) : sleeves({}),
      );

      render(<AllocationCharts />);
      await screen.findByText(/Instrument Types/);
      expect(mockGetSleeves).not.toHaveBeenCalled();
      fireEvent.click(screen.getByRole("button", { name: "Sleeves" }));

      await waitFor(() => expect(mockGetSleeves).toHaveBeenCalledTimes(2));
      const slices = screen.getByTestId("pie-slices");
      await waitFor(() =>
        expect(within(slices).getAllByTestId("slice-row").map((el) => el.textContent)).toEqual([
          "Speculative: 100",
          "Core: 80",
        ]),
      );
      expect(screen.getByTestId("sleeve-note")).toBeInTheDocument();
    });

    it("shows everything as core when no owner has sleeves", async () => {
      mockGetGroupPortfolio.mockResolvedValueOnce(samplePortfolio);
      mockGetSleeves.mockResolvedValue({
        sleeves: [{ id: "core", name: "Core", size_pct: 100, targets: {}, strategy: null }],
        assignments: {},
        holdings: [],
      });
      render(<AllocationCharts />, "/allocation?view=sleeve");
      const slices = await screen.findByTestId("pie-slices");
      await waitFor(() =>
        expect(within(slices).getAllByTestId("slice-row").map((el) => el.textContent)).toEqual(["Core: 100"]),
      );
    });

    it("shows the error when sleeves cannot be loaded", async () => {
      mockGetGroupPortfolio.mockResolvedValueOnce(samplePortfolio);
      mockGetSleeves.mockRejectedValue(new Error("sleeve boom"));
      render(<AllocationCharts />, "/allocation?view=sleeve");
      expect(await screen.findByText("sleeve boom")).toBeInTheDocument();
      expect(screen.getByTestId("no-slices")).toBeInTheDocument();
    });
  });

  it("renders contribution_pct as percentage points, not a fraction (#10030)", async () => {
    // Backend `_aggregate_by_field` stores contribution_pct in percentage
    // points (12.0 for 12%), so the relative-view tick must read "12.0%",
    // not "0.1%". This pins the scale: a fraction-based formatter fails here.
    mockGetGroupPortfolio.mockResolvedValueOnce(samplePortfolio);
    mockGetGroupCurrencies.mockResolvedValueOnce([
      {
        quote_currency: "GBP",
        market_value_gbp: 100,
        gain_gbp: 12,
        cost_gbp: 100,
        contribution_pct: 12,
        currency: "GBP",
      },
    ]);

    render(<AllocationCharts />, "/allocation?view=currency");

    await waitFor(() => expect(mockGetGroupCurrencies).toHaveBeenCalled());
    const ticks = await screen.findAllByTestId("y-axis-tick");
    const rendered = ticks.map((el) => el.textContent);
    expect(rendered).toContain("12.0%");
    expect(rendered.some((t) => t?.endsWith("%"))).toBe(true);
  });

  it("shows each slice's percentage in the legend and tooltip", async () => {
    mockGetGroupPortfolio.mockResolvedValueOnce(
      buildPortfolio([
        { ...baseHolding, ticker: "AAA", instrument_type: "equity", market_value_gbp: 75 },
        { ...baseHolding, ticker: "BBB", instrument_type: "etf", market_value_gbp: 25 },
      ]),
    );

    render(<AllocationCharts />);

    await waitFor(() => expect(screen.getAllByTestId("slice-row")).toHaveLength(2));
    const legend = chartFormatters.legend!("Equity", { payload: { value: 75 } });
    expect(legend).toMatch(/^Equity: .*75.* \(75\.00%\)$/);
    expect(chartFormatters.tooltip!(25, "ETF", { payload: { value: 25 } })).toMatch(/25.* \(25\.00%\)$/);
  });

  describe("look-through views (#9974)", () => {
    const bucket = (label: string, value_gbp: number) => ({ label, value_gbp, weight_pct: value_gbp / 10 });
    const lookThrough = (countries: ReturnType<typeof bucket>[]): LookThroughExposure => ({
      total_value_gbp: 1000,
      countries,
      sectors: [bucket("Information Technology", 700), bucket("Financials", 300)],
      holdings: [
        {
          key: "US5949181045",
          name: "Microsoft",
          isin: "US5949181045",
          kind: "security",
          value_gbp: 300,
          weight_pct: 30,
          direct_value_gbp: 200,
          via_funds_value_gbp: 100,
          sources: [
            { ticker: "MSFT.N", value_gbp: 200 },
            { ticker: "VWRL.L", value_gbp: 100 },
          ],
        },
        {
          key: "OTHER-IN-FUNDS",
          name: "Other holdings in funds",
          isin: null,
          kind: "other",
          value_gbp: 700,
          weight_pct: 70,
          direct_value_gbp: 0,
          via_funds_value_gbp: 700,
          sources: [{ ticker: "VWRL.L", value_gbp: 700 }],
        },
      ],
      coverage: {
        looked_through_value_gbp: 800,
        direct_value_gbp: 200,
        not_covered_value_gbp: 50,
        cash_value_gbp: 0,
        funds: [{ ticker: "VWRL.L", name: "All-World", value_gbp: 800, source: "morningstar", as_of: "2026-08-31" }],
        not_covered: [{ ticker: "HICL.L", name: "HICL", value_gbp: 50 }],
      },
    });

    it("fetches look-through only when a look-through view is opened", async () => {
      mockGetGroupPortfolio.mockResolvedValueOnce(samplePortfolio);
      mockGetGroupLookThrough.mockResolvedValueOnce(
        lookThrough([bucket("United States", 600), bucket("Japan", 400)]),
      );

      render(<AllocationCharts />);
      await screen.findByRole("button", { name: "Countries (look-through)" });
      expect(mockGetGroupLookThrough).not.toHaveBeenCalled();

      fireEvent.click(await screen.findByRole("button", { name: "Countries (look-through)" }));

      await waitFor(() => expect(mockGetGroupLookThrough).toHaveBeenCalledWith("all"));
      await waitFor(() =>
        expect(screen.getAllByTestId("slice-row").map((el) => el.textContent)).toEqual([
          "United States: 600",
          "Japan: 400",
        ]),
      );
      expect(screen.getByTestId("look-through-note")).toBeInTheDocument();
    });

    it("uses the owner look-through endpoint when an owner is selected", async () => {
      mockGetGroupLookThrough.mockClear();
      mockGetGroupPortfolio.mockResolvedValueOnce(samplePortfolio);
      mockGetOwnerLookThrough.mockResolvedValueOnce(lookThrough([bucket("Japan", 400)]));

      render(<AllocationCharts />, "/allocation?view=lt-country&owner=alice");

      await waitFor(() => expect(mockGetOwnerLookThrough).toHaveBeenCalledWith("alice"));
      await waitFor(() =>
        expect(screen.getAllByTestId("slice-row").map((el) => el.textContent)).toEqual([
          "Japan: 400",
        ]),
      );
      expect(mockGetGroupLookThrough).not.toHaveBeenCalled();
    });

    it("reports coverage and funds that were not looked through", async () => {
      mockGetGroupPortfolio.mockResolvedValueOnce(samplePortfolio);
      mockGetGroupLookThrough.mockResolvedValueOnce(lookThrough([bucket("United States", 1000)]));

      render(<AllocationCharts />, "/allocation?view=lt-sector");

      expect(await screen.findByTestId("look-through-coverage")).toHaveTextContent(/1 funds .* 2026-08-31/);
      expect(screen.getByTestId("look-through-not-covered")).toHaveTextContent("HICL.L");
      await waitFor(() =>
        expect(screen.getAllByTestId("slice-row").map((el) => el.textContent)).toEqual([
          "Information Technology: 700",
          "Financials: 300",
        ]),
      );
    });

    it("shows coverage as % of the look-through total under relative view (#10022)", async () => {
      // Inherit the default config and only flip relative view on, so the
      // page's other config reads behave as in the tests above.
      const RelativeView = ({ children }: { children: ReactNode }) => {
        const config = useConfig();
        return (
          <configContext.Provider value={{ ...config, relativeViewEnabled: true }}>
            {children}
          </configContext.Provider>
        );
      };
      mockGetGroupPortfolio.mockResolvedValueOnce(samplePortfolio);
      mockGetGroupLookThrough.mockResolvedValueOnce(lookThrough([bucket("United States", 1000)]));

      render(
        <RelativeView>
          <AllocationCharts />
        </RelativeView>,
        "/allocation?view=lt-sector",
      );

      // 800 / 1000 and 50 / 1000 of lookThrough.total_value_gbp.
      const coverage = await screen.findByTestId("look-through-coverage");
      expect(coverage).toHaveTextContent("80.0%");
      expect(coverage).not.toHaveTextContent("£");
      const notCovered = screen.getByTestId("look-through-not-covered");
      expect(notCovered).toHaveTextContent("5.0%");
      expect(notCovered).not.toHaveTextContent("£");
    });

    it("folds the tail of many countries into one Other slice", async () => {
      mockGetGroupPortfolio.mockResolvedValueOnce(samplePortfolio);
      const many = Array.from({ length: 15 }, (_, i) => bucket(`C${i}`, 100 - i));
      mockGetGroupLookThrough.mockResolvedValueOnce(lookThrough(many));

      render(<AllocationCharts />, "/allocation?view=lt-country");

      await waitFor(() => expect(screen.getAllByTestId("slice-row")).toHaveLength(12));
      const rows = screen.getAllByTestId("slice-row").map((el) => el.textContent);
      // 11 largest kept; C11..C14 (89+88+87+86) folded together.
      expect(rows[11]).toBe("Other: 350");
    });

    it("lists combined holdings with direct and via-fund values", async () => {
      mockGetGroupPortfolio.mockResolvedValueOnce(samplePortfolio);
      mockGetGroupLookThrough.mockResolvedValueOnce(lookThrough([bucket("United States", 1000)]));

      render(<AllocationCharts />, "/allocation?view=lt-holdings");

      const table = await screen.findByRole("table", { name: "Underlying holdings" });
      const msft = within(table).getByText("Microsoft").closest("tr") as HTMLElement;
      expect(within(msft).getByRole("link", { name: "MSFT.N" })).toHaveAttribute("href", "/research/MSFT.N");
      expect(within(msft).getByRole("link", { name: "VWRL.L" })).toBeInTheDocument();
      expect(within(table).getByText(/Other holdings in funds/)).toBeInTheDocument();
      expect(screen.queryByTestId("pie-chart")).not.toBeInTheDocument();
    });

    it("shows the look-through endpoint error", async () => {
      mockGetGroupPortfolio.mockResolvedValueOnce(samplePortfolio);
      mockGetGroupLookThrough.mockRejectedValueOnce(new Error("look-through boom"));

      render(<AllocationCharts />, "/allocation?view=lt-holdings");

      expect(await screen.findByText("look-through boom")).toBeInTheDocument();
    });
  });
});
