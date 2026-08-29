import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Screener } from "@/pages/Screener";
import * as api from "@/api";

vi.mock("@/api");

const mockGetScreener = vi.mocked(api.getScreener);

describe("Screener", () => {
  it("has a heading matching its menu label (#7199)", async () => {
    mockGetScreener.mockResolvedValue([]);
    render(<Screener />);
    // Matches app.modes.screener ("Screener & Query") exactly, per #7199's
    // success criterion.
    expect(
      await screen.findByRole("heading", { name: "Screener & Query" }),
    ).toBeInTheDocument();
  });

  it("probes capability with a real sentinel ticker, not an empty list (#7199)", async () => {
    // A pro-enabled backend 400s on an empty ticker list ("No tickers
    // supplied") before it ever gets a chance to 200 — require_core runs
    // first, but so does the ticker-emptiness check once that passes. An
    // empty-list probe can therefore never positively confirm availability;
    // it can only ever prove the negative (402) case. A real ticker is
    // required so a pro deployment's probe gets a genuine success response.
    mockGetScreener.mockResolvedValue([]);
    render(<Screener />);
    await screen.findByLabelText("Watchlist");
    const [tickers] = mockGetScreener.mock.calls[0] ?? [];
    expect(tickers).toEqual(expect.arrayContaining([expect.any(String)]));
    expect(tickers.length).toBeGreaterThan(0);
  });

  it("gates the form up front, in plain language, when screening isn't available (#7199)", async () => {
    const gatedError = Object.assign(new Error("HTTP 402 - Payment Required"), {
      status: 402,
    });
    mockGetScreener.mockRejectedValueOnce(gatedError);

    render(<Screener />);

    const gate = await screen.findByText("Screening unavailable");
    expect(gate).toBeInTheDocument();
    expect(
      screen.getByText(
        "Screening isn't available in this deployment. Contact your administrator to enable this feature.",
      ),
    ).toBeInTheDocument();

    // The full filter form must not render at all in this state — the whole
    // point is to not let the user fill in two dozen fields for a Run that
    // will always 402.
    expect(screen.queryByLabelText("Watchlist")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run" })).not.toBeInTheDocument();
  });

  it("shows the plain-language gate, not the raw backend string, when Run itself hits a 402 (#7199)", async () => {
    // The mount probe can fail open to "available" on a non-402 error (a
    // timeout, a 5xx) — Run is then the request that actually discovers the
    // real 402. This must not surface the raw backend `detail` (package
    // name, GitHub URL) the way the untouched code used to.
    const gatedError = Object.assign(
      new Error(
        "Screener is not available: This feature requires the allotmint-pro package, which is not installed in this deployment. See https://github.com/leonarduk/allotmint-pro for upgrade options.",
      ),
      { status: 402 },
    );
    mockGetScreener.mockResolvedValueOnce([]); // mount probe: succeeds
    mockGetScreener.mockRejectedValueOnce(gatedError); // Run: 402

    render(<Screener />);
    fireEvent.change(await screen.findByLabelText(/Tickers/i), {
      target: { value: "AAA" },
    });
    fireEvent.submit(screen.getByText(/Run/i).closest("form")!);

    const gate = await screen.findByText("Screening unavailable");
    expect(gate).toBeInTheDocument();
    expect(screen.queryByText(/allotmint-pro|github\.com/i)).not.toBeInTheDocument();
  });

  it("renders the form as normal when screening is available", async () => {
    mockGetScreener.mockResolvedValue([]);
    render(<Screener />);

    expect(await screen.findByLabelText("Watchlist")).toBeInTheDocument();
    expect(screen.queryByText("Screening unavailable")).not.toBeInTheDocument();
  });

  it("renders new ratio columns", async () => {
    // #7199: Screener now probes capability with a cheap getScreener([], {})
    // call on mount before it renders the filter form, so the mock here
    // must serve both that probe and the real submitted query — a `*Once`
    // mock would be consumed by the probe and leave the Run call unmocked.
    mockGetScreener.mockResolvedValue([
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

    // Form only renders once the mount-time capability probe resolves.
    fireEvent.change(await screen.findByLabelText(/Tickers/i), { target: { value: "AAA" } });
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

  it("does not emit duplicate-key warnings when the same ticker appears twice (#6505)", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    // See the note above: `mockResolvedValue` (not `*Once`) so the mount-time
    // capability probe and the real Run call both get a response.
    mockGetScreener.mockResolvedValue([
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
    fireEvent.change(await screen.findByLabelText(/Tickers/i), { target: { value: "CASH" } });
    fireEvent.submit(screen.getByText(/Run/i).closest("form")!);

    expect(await screen.findAllByText("CASH")).toHaveLength(2);
    const keyWarnings = errorSpy.mock.calls.filter((args) =>
      String(args[0]).includes("same key"),
    );
    expect(keyWarnings).toEqual([]);
    errorSpy.mockRestore();
  });
});

