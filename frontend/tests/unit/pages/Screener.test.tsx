import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { Screener } from "@/pages/Screener";
import * as api from "@/api";

vi.mock("@/api");

const mockGetScreener = vi.mocked(api.getScreener);
const mockCheckScreenerAvailable = vi.mocked(api.checkScreenerAvailable);

describe("Screener", () => {
  beforeEach(() => {
    // Default every test to an available screener unless a test overrides
    // this -- the gate probe (#7221) must not affect existing form-render
    // and submit tests.
    mockCheckScreenerAvailable.mockResolvedValue(true);
  });

  it("renders a page heading and description before the form", () => {
    render(<Screener />);

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

    render(<Screener />);

    // Success bullet 2: unavailability (or, here, "don't know yet") must be
    // stated before any input is requested -- the 24-filter form must not
    // flash on screen, fully interactive, before the probe settles.
    expect(screen.queryByLabelText(/Tickers/i)).not.toBeInTheDocument();
    expect(
      screen.getByText(/checking screener availability/i),
    ).toBeInTheDocument();
  });

  it("hides the filter form and shows an honest message when the screener is gated (#7221)", async () => {
    mockCheckScreenerAvailable.mockResolvedValue(false);

    render(<Screener />);

    expect(
      await screen.findByText(/doesn't include the fundamentals screener/i),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText(/Tickers/i)).not.toBeInTheDocument();
    // The gate copy must never leak the internal package name or repo URL.
    expect(screen.queryByText(/allotmint-pro/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/github\.com/i)).not.toBeInTheDocument();
  });

  it("renders the form once the gate check resolves available", async () => {
    render(<Screener />);

    expect(await screen.findByLabelText(/Tickers/i)).toBeInTheDocument();
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

    render(<Screener />);

    fireEvent.change(await screen.findByLabelText(/Tickers/i), {
      target: { value: "AAA" },
    });
    fireEvent.submit(screen.getByText(/Run/i).closest("form")!);

    expect(
      await screen.findByText(/doesn't include the fundamentals screener/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/allotmint-pro/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/github\.com/i)).not.toBeInTheDocument();
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

    render(<Screener />);

    fireEvent.change(await screen.findByLabelText(/Tickers/i), {
      target: { value: "AAA" },
    });
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

    render(<Screener />);
    fireEvent.change(screen.getByLabelText(/Tickers/i), { target: { value: "AAA" } });
    fireEvent.submit(screen.getByText(/Run/i).closest("form")!);

    const tip = await screen.findByRole("button", { name: "What does PEG mean?" });
    expect(tip).toBeInTheDocument();

    fireEvent.click(tip);
    const link = within(tip.parentElement as HTMLElement).getByRole("link", {
      name: "Learn more",
    });
    expect(link).toHaveAttribute("href", "/metrics-explained#peg-ratio");
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

    render(<Screener />);
    fireEvent.change(await screen.findByLabelText(/Tickers/i), {
      target: { value: "CASH" },
    });
    fireEvent.submit(screen.getByText(/Run/i).closest("form")!);

    expect(await screen.findAllByText("CASH")).toHaveLength(2);
    const keyWarnings = errorSpy.mock.calls.filter((args) =>
      String(args[0]).includes("same key"),
    );
    expect(keyWarnings).toEqual([]);
    errorSpy.mockRestore();
  });
});

