import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import { Screener } from "@/pages/Screener";
import * as api from "@/api";

vi.mock("@/api");
vi.mock("@/components/InstrumentDetail", () => ({
  InstrumentDetail: ({ ticker }: { ticker: string }) => (
    <div data-testid="instrument-detail">{ticker}</div>
  ),
}));

const mockGetScreener = vi.mocked(api.getScreener);
const mockCheckScreenerAvailable = vi.mocked(api.checkScreenerAvailable);

function ResearchStub() {
  const { ticker } = useParams();
  return <p>research page for {ticker}</p>;
}

// Ticker cells are router <Link>s, so the page needs a router context.
const renderScreener = () =>
  render(
    <MemoryRouter initialEntries={["/screener"]}>
      <Routes>
        <Route path="/screener" element={<Screener />} />
        <Route path="/research/:ticker" element={<ResearchStub />} />
      </Routes>
    </MemoryRouter>,
  );

// The page defaults to the FTSE 100 watchlist, so the free-text Tickers
// input only appears once "Custom" is chosen.
async function enterCustomTickers(value: string) {
  fireEvent.change(await screen.findByLabelText("Watchlist"), {
    target: { value: "Custom" },
  });
  fireEvent.change(screen.getByLabelText(/Tickers/i), { target: { value } });
}

describe("Screener", () => {
  beforeEach(() => {
    // Default every test to an available screener unless a test overrides
    // this -- the gate probe (#7221) must not affect existing form-render
    // and submit tests.
    mockCheckScreenerAvailable.mockResolvedValue(true);
  });

  it("renders a page heading and description before the form", () => {
    renderScreener();

    expect(
      screen.getByRole("heading", { name: /screener/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/filter a watchlist or a custom list of tickers/i),
    ).toBeInTheDocument();
  });

  it("does not render the interactive form while the gate check is still in flight (#7221)", () => {
    // A probe that never resolves during this test -- simulates the
    // in-flight window between mount and the gate check settling.
    mockCheckScreenerAvailable.mockReturnValue(new Promise(() => {}));

    renderScreener();

    // Success bullet 2: unavailability (or, here, "don't know yet") must be
    // stated before any input is requested -- the 24-filter form must not
    // flash on screen, fully interactive, before the probe settles.
    expect(screen.queryByLabelText("Watchlist")).not.toBeInTheDocument();
    expect(
      screen.getByText(/checking screener availability/i),
    ).toBeInTheDocument();
  });

  it("hides the filter form and shows an honest message when the screener is gated (#7221)", async () => {
    mockCheckScreenerAvailable.mockResolvedValue(false);

    renderScreener();

    expect(
      await screen.findByText(/doesn't include the fundamentals screener/i),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Watchlist")).not.toBeInTheDocument();
    // The gate copy must never leak the internal package name or repo URL.
    expect(screen.queryByText(/allotmint-pro/i)).not.toBeInTheDocument();
    expect(screen.queryByText("github.com", { exact: false })).not.toBeInTheDocument();
  });

  it("renders the form once the gate check resolves available", async () => {
    renderScreener();

    expect(await screen.findByLabelText("Watchlist")).toBeInTheDocument();
  });

  it("sanitizes a 402 raised mid-submit instead of showing the raw backend detail", async () => {
    mockGetScreener.mockRejectedValueOnce(
      Object.assign(
        new Error(
          "Screener is not available: This feature requires the allotmint-pro package, which is not installed in this deployment. See https://github.com/leonarduk/allotmint-pro for upgrade options.",
        ),
        { status: 402 },
      ),
    );

    renderScreener();

    await enterCustomTickers("AAA");
    fireEvent.submit(screen.getByText(/Run/i).closest("form")!);

    expect(
      await screen.findByText(/doesn't include the fundamentals screener/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/allotmint-pro/i)).not.toBeInTheDocument();
    expect(screen.queryByText("github.com", { exact: false })).not.toBeInTheDocument();
  });

  it("renders new ratio columns", async () => {
    mockGetScreener.mockResolvedValueOnce([
      {
        rank: 1,
        ticker: "AAA",
        name: "AAA Corp",
        peg_ratio: 1,
        pe_ratio: 10,
        de_ratio: 0.5,
        lt_de_ratio: 0.3,
        interest_coverage: 10,
        current_ratio: 2,
        quick_ratio: 1.5,
        fcf: 1000,
        eps: null,
        gross_margin: null,
        operating_margin: null,
        net_margin: null,
        ebitda_margin: null,
        roa: null,
        roe: null,
        roi: null,
        dividend_yield: null,
        dividend_payout_ratio: null,
        beta: null,
        shares_outstanding: null,
        float_shares: null,
        market_cap: null,
        high_52w: null,
        low_52w: null,
        avg_volume: null,
      },
    ]);

    renderScreener();

    await enterCustomTickers("AAA");
    fireEvent.change(screen.getByLabelText(/Max LT D\/E/i), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText(/Min Interest Coverage/i), { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText(/Min Current Ratio/i), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText(/Min Quick Ratio/i), { target: { value: "1" } });

    fireEvent.submit(screen.getByText(/Run/i).closest("form")!);

    await waitFor(() => expect(mockGetScreener).toHaveBeenCalled());
    expect(mockGetScreener).toHaveBeenCalledWith(
      ["AAA"],
      expect.objectContaining({
        lt_de_max: 1,
        interest_coverage_min: 5,
        current_ratio_min: 1,
        quick_ratio_min: 1,
      })
    );

    expect(await screen.findByText("LT D/E")).toBeInTheDocument();
    expect(screen.getByText("IntCov")).toBeInTheDocument();
    expect(screen.getByText("Curr")).toBeInTheDocument();
    expect(screen.getByText("Quick")).toBeInTheDocument();

    expect(screen.getByText("0.3")).toBeInTheDocument();
    expect(screen.getAllByText("10")).toHaveLength(2);
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("1.5")).toBeInTheDocument();
  });

  it("sends valuation filters and shows P/B, P/S, EV/EBITDA and growth columns (#8557)", async () => {
    mockGetScreener.mockResolvedValueOnce([
      {
        rank: 1,
        ticker: "AAA",
        name: "AAA Corp",
        peg_ratio: null,
        pe_ratio: null,
        de_ratio: null,
        lt_de_ratio: null,
        interest_coverage: null,
        current_ratio: null,
        quick_ratio: null,
        fcf: null,
        eps: null,
        gross_margin: null,
        operating_margin: null,
        net_margin: null,
        ebitda_margin: null,
        roa: null,
        roe: null,
        roi: null,
        dividend_yield: null,
        dividend_payout_ratio: null,
        beta: null,
        shares_outstanding: null,
        float_shares: null,
        market_cap: null,
        high_52w: null,
        low_52w: null,
        avg_volume: null,
        pb_ratio: 1.25,
        ps_ratio: 3.5,
        ev_ebitda: 7.75,
        revenue_growth: 0.12,
        earnings_growth: null,
      },
    ]);

    renderScreener();

    await enterCustomTickers("AAA");
    fireEvent.change(screen.getByLabelText("Max P/B"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Max P/S"), { target: { value: "4" } });
    fireEvent.change(screen.getByLabelText("Max EV/EBITDA"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText("Min Revenue Growth"), { target: { value: "0.05" } });
    fireEvent.change(screen.getByLabelText("Min Earnings Growth"), { target: { value: "-0.1" } });

    fireEvent.submit(screen.getByText(/Run/i).closest("form")!);

    await waitFor(() => expect(mockGetScreener).toHaveBeenCalled());
    expect(mockGetScreener).toHaveBeenCalledWith(
      ["AAA"],
      expect.objectContaining({
        pb_max: 2,
        ps_max: 4,
        ev_ebitda_max: 10,
        revenue_growth_min: 0.05,
        earnings_growth_min: -0.1,
      }),
    );

    expect(await screen.findByText("EV/EBITDA")).toBeInTheDocument();
    expect(screen.getByText("P/B")).toBeInTheDocument();
    expect(screen.getByText("Rev Growth")).toBeInTheDocument();
    expect(screen.getByText("1.25")).toBeInTheDocument();
    expect(screen.getByText("3.5")).toBeInTheDocument();
    expect(screen.getByText("7.75")).toBeInTheDocument();
    expect(screen.getByText("0.12")).toBeInTheDocument();

    const tip = screen.getByRole("button", { name: "What does EV/EBITDA mean?" });
    fireEvent.click(tip);
    expect(
      within(tip.parentElement as HTMLElement).getByRole("link", { name: "Learn more" }),
    ).toHaveAttribute("href", "/metrics-explained#ev-ebitda");
  });

  it("attaches an InfoTip to ratio column headers linking to the glossary (#7230)", async () => {
    mockGetScreener.mockResolvedValueOnce([
      {
        rank: 1,
        ticker: "AAA",
        name: "AAA Corp",
        peg_ratio: 1,
        pe_ratio: 10,
        de_ratio: 0.5,
        lt_de_ratio: 0.3,
        interest_coverage: 10,
        current_ratio: 2,
        quick_ratio: 1.5,
        fcf: 1000,
        eps: null,
        gross_margin: null,
        operating_margin: null,
        net_margin: null,
        ebitda_margin: null,
        roa: null,
        roe: null,
        roi: null,
        dividend_yield: null,
        dividend_payout_ratio: null,
        beta: null,
        shares_outstanding: null,
        float_shares: null,
        market_cap: null,
        high_52w: null,
        low_52w: null,
        avg_volume: null,
      },
    ]);

    renderScreener();
    await enterCustomTickers("AAA");
    fireEvent.submit(screen.getByText(/Run/i).closest("form")!);

    const tip = await screen.findByRole("button", { name: "What does PEG mean?" });
    expect(tip).toBeInTheDocument();

    fireEvent.click(tip);
    const link = within(tip.parentElement as HTMLElement).getByRole("link", {
      name: "Learn more",
    });
    expect(link).toHaveAttribute("href", "/metrics-explained#peg-ratio");
  });

  it("shows the name and sector when hovering a ticker", async () => {
    mockGetScreener.mockResolvedValueOnce([
      { rank: 1, ticker: "AAA", name: "AAA Corp", sector: "Energy" },
      { rank: 2, ticker: "BBB", name: "BBB Corp", sector: null },
      { rank: 3, ticker: "CCC", name: null, sector: null },
    ]);

    renderScreener();
    await enterCustomTickers("AAA,BBB,CCC");
    fireEvent.submit(screen.getByText(/Run/i).closest("form")!);

    expect(await screen.findByText("AAA")).toHaveAttribute("title", "AAA Corp — Energy");
    expect(screen.getByText("BBB")).toHaveAttribute("title", "BBB Corp");
    expect(screen.getByText("CCC")).not.toHaveAttribute("title");
  });

  it("links each ticker to its research page without opening the row's detail panel", async () => {
    mockGetScreener.mockResolvedValueOnce([{ rank: 1, ticker: "GLEN.L", name: "Glencore" }]);

    renderScreener();
    await enterCustomTickers("GLEN.L");
    fireEvent.submit(screen.getByText(/Run/i).closest("form")!);

    const link = await screen.findByRole("link", { name: "GLEN.L" });
    expect(link).toHaveAttribute("href", "/research/GLEN.L");
    fireEvent.click(link);
    expect(screen.queryByTestId("instrument-detail")).not.toBeInTheDocument();
    expect(await screen.findByText("research page for GLEN.L")).toBeInTheDocument();
  });

  it("still opens the detail panel when the rest of the row is clicked", async () => {
    mockGetScreener.mockResolvedValueOnce([{ rank: 1, ticker: "GLEN.L", name: "Glencore" }]);

    renderScreener();
    await enterCustomTickers("GLEN.L");
    fireEvent.submit(screen.getByText(/Run/i).closest("form")!);

    fireEvent.click((await screen.findByRole("link", { name: "GLEN.L" })).closest("tr")!);
    expect(screen.getByTestId("instrument-detail")).toHaveTextContent("GLEN.L");
  });

  it("renders every body cell under its matching column header", async () => {
    // Header label -> row field, in header order. Each field gets a distinct
    // value (< 1000 so locale grouping never alters it) so a misplaced cell
    // is caught by index, not just by presence.
    const columns: [string, string][] = [
      ["PEG", "peg_ratio"],
      ["P/E", "pe_ratio"],
      ["D/E", "de_ratio"],
      ["LT D/E", "lt_de_ratio"],
      ["IntCov", "interest_coverage"],
      ["Curr", "current_ratio"],
      ["Quick", "quick_ratio"],
      ["FCF", "fcf"],
      ["EPS", "eps"],
      ["Gross Margin", "gross_margin"],
      ["Op Margin", "operating_margin"],
      ["Net Margin", "net_margin"],
      ["EBITDA Margin", "ebitda_margin"],
      ["ROA", "roa"],
      ["ROE", "roe"],
      ["ROI", "roi"],
      ["Div%", "dividend_yield"],
      ["Payout", "dividend_payout_ratio"],
      ["Beta", "beta"],
      ["Shares", "shares_outstanding"],
      ["Float", "float_shares"],
      ["MktCap", "market_cap"],
      ["52wH", "high_52w"],
      ["52wL", "low_52w"],
      ["AvgVol", "avg_volume"],
    ];
    const row: Record<string, unknown> = { rank: 1, ticker: "AAA", name: "AAA Corp" };
    columns.forEach(([, field], i) => {
      row[field] = 101 + i;
    });
    mockGetScreener.mockResolvedValueOnce([row as never]);

    const { container } = renderScreener();
    await enterCustomTickers("AAA");
    fireEvent.submit(screen.getByText(/Run/i).closest("form")!);
    await screen.findByText("AAA");

    // The header's own label is its first text node; the InfoTip follows it.
    const headers = screen
      .getAllByRole("columnheader")
      .map((th) => th.childNodes[0]?.textContent?.trim());
    const cells = Array.from(
      container.querySelectorAll("tbody tr:first-child td"),
    ).map((td) => td.textContent?.trim());

    expect(cells).toHaveLength(headers.length);
    expect(cells[headers.indexOf("Rank")]).toBe("1");
    // The ticker cell also carries the add-to-watchlist star.
    expect(cells[headers.indexOf("Ticker")]).toBe("AAA☆");
    columns.forEach(([label], i) => {
      const idx = headers.indexOf(label);
      expect(idx, `header ${label}`).toBeGreaterThan(-1);
      expect(cells[idx], `cell under ${label}`).toBe(String(101 + i));
    });
  });

  it("does not emit duplicate-key warnings when the same ticker appears twice (#6505)", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    mockGetScreener.mockResolvedValueOnce([
      {
        rank: 1,
        ticker: "CASH",
        name: "Cash GBP",
        peg_ratio: null,
        pe_ratio: null,
        de_ratio: null,
        lt_de_ratio: null,
        interest_coverage: null,
        current_ratio: null,
        quick_ratio: null,
        fcf: null,
        eps: null,
        gross_margin: null,
        operating_margin: null,
        net_margin: null,
        ebitda_margin: null,
        roa: null,
        roe: null,
        roi: null,
        dividend_yield: null,
        dividend_payout_ratio: null,
        beta: null,
        shares_outstanding: null,
        float_shares: null,
        market_cap: null,
        high_52w: null,
        low_52w: null,
        avg_volume: null,
      },
      {
        rank: 2,
        ticker: "CASH",
        name: "Cash L",
        peg_ratio: null,
        pe_ratio: null,
        de_ratio: null,
        lt_de_ratio: null,
        interest_coverage: null,
        current_ratio: null,
        quick_ratio: null,
        fcf: null,
        eps: null,
        gross_margin: null,
        operating_margin: null,
        net_margin: null,
        ebitda_margin: null,
        roa: null,
        roe: null,
        roi: null,
        dividend_yield: null,
        dividend_payout_ratio: null,
        beta: null,
        shares_outstanding: null,
        float_shares: null,
        market_cap: null,
        high_52w: null,
        low_52w: null,
        avg_volume: null,
      },
    ]);

    renderScreener();
    await enterCustomTickers("CASH");
    fireEvent.submit(screen.getByText(/Run/i).closest("form")!);

    expect(await screen.findAllByText("CASH")).toHaveLength(2);
    const keyWarnings = errorSpy.mock.calls.filter((args) =>
      String(args[0]).includes("same key"),
    );
    expect(keyWarnings).toEqual([]);
    errorSpy.mockRestore();
  });
  it("prefills a conservative default screen against the FTSE 100", async () => {
    mockGetScreener.mockResolvedValueOnce([]);
    renderScreener();

    expect(await screen.findByLabelText("Watchlist")).toHaveValue("FTSE 100");
    expect(screen.getByLabelText("Max P/E")).toHaveValue(25);
    expect(screen.getByLabelText("Min Current Ratio")).toHaveValue(1);
    expect(screen.getByLabelText("Min ROE")).toHaveValue(0.1);
    // Unit-ambiguous metrics stay blank rather than guessing a scale.
    expect(screen.getByLabelText("Max D/E")).toHaveValue(null);
    expect(screen.getByLabelText("Min Dividend Yield")).toHaveValue(null);

    fireEvent.submit(screen.getByText("Run").closest("form")!);

    await waitFor(() => expect(mockGetScreener).toHaveBeenCalled());
    const [symbols, criteria] = mockGetScreener.mock.calls.at(-1)!;
    expect(symbols).toContain("AZN.L");
    expect(criteria).toEqual({ pe_max: 25, current_ratio_min: 1, roe_min: 0.1 });
    expect(
      await screen.findByText(/no tickers matched these filters/i),
    ).toBeInTheDocument();
  });

  it("clears and restores the default filters", async () => {
    renderScreener();

    fireEvent.change(await screen.findByLabelText("Max Beta"), {
      target: { value: "1.2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByLabelText("Max P/E")).toHaveValue(null);
    expect(screen.getByLabelText("Max Beta")).toHaveValue(null);

    fireEvent.change(screen.getByLabelText("Watchlist"), {
      target: { value: "S&P 500" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Reset to defaults" }));
    expect(screen.getByLabelText("Watchlist")).toHaveValue("FTSE 100");
    expect(screen.getByLabelText("Max P/E")).toHaveValue(25);
  });

  it("labels the 52-week-high filter as a high, not a low", async () => {
    mockGetScreener.mockResolvedValueOnce([]);
    renderScreener();

    fireEvent.change(await screen.findByLabelText("Max 52W High"), {
      target: { value: "150" },
    });
    expect(screen.queryByLabelText("Max 52W Low")).not.toBeInTheDocument();
    fireEvent.submit(screen.getByText("Run").closest("form")!);

    await waitFor(() => expect(mockGetScreener).toHaveBeenCalled());
    expect(mockGetScreener.mock.calls.at(-1)![1]).toMatchObject({
      high_52w_max: 150,
    });
  });

  it("explains instead of silently ignoring Run with no custom tickers", async () => {
    mockGetScreener.mockClear();
    renderScreener();

    fireEvent.change(await screen.findByLabelText("Watchlist"), {
      target: { value: "Custom" },
    });
    fireEvent.submit(screen.getByText("Run").closest("form")!);

    expect(
      await screen.findByText(/enter at least one ticker/i),
    ).toBeInTheDocument();
    expect(mockGetScreener).not.toHaveBeenCalled();
  });

  it("marks fraction-scaled filters with their scale", async () => {
    renderScreener();

    expect(await screen.findByLabelText("Min Gross Margin")).toHaveAttribute(
      "placeholder",
      "0.10 = 10%",
    );
    expect(screen.getByLabelText("Min Market Cap")).toHaveAttribute("step", "1");
  });

  it("never sends a decimal for an integer-typed filter", async () => {
    mockGetScreener.mockResolvedValueOnce([]);
    renderScreener();

    fireEvent.change(await screen.findByLabelText("Min Avg Volume"), {
      target: { value: "1500.6" },
    });
    fireEvent.submit(screen.getByText("Run").closest("form")!);

    await waitFor(() => expect(mockGetScreener).toHaveBeenCalled());
    expect(mockGetScreener.mock.calls.at(-1)![1]).toMatchObject({
      avg_volume_min: 1501,
    });
  });
});

