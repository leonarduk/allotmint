import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { InstrumentAllocationPanel, LookThroughCoverageNote } from "@/components/LookThrough";
import { foldWeightRows } from "@/lib/lookThrough";
import * as api from "@/api";
import type { InstrumentAllocation } from "@/types";

vi.mock("@/api", () => ({ getInstrumentAllocation: vi.fn(), refreshInstrumentLookThrough: vi.fn() }));
const mockGetAllocation = vi.mocked(api.getInstrumentAllocation);
const mockRefresh = vi.mocked(api.refreshInstrumentLookThrough);

const allocation = (overrides: Partial<InstrumentAllocation> = {}): InstrumentAllocation => ({
  ticker: "MINV.L",
  name: "iShares Edge MSCI World Minimum Volatility",
  kind: "fund",
  source: "morningstar",
  source_url: "https://global.morningstar.com/en-gb/search?query=IE00B8FHGS14",
  as_of: "2026-10-05",
  fetched: "2026-10-07",
  holdings_count: 380,
  asset_mix: { equity: 99.5, cash: 0.5 },
  countries: [
    { label: "United States", weight_pct: 66.2 },
    { label: "Japan", weight_pct: 11.1 },
  ],
  sectors: [{ label: "Information Technology", weight_pct: 24.6 }],
  top_holdings: [
    { name: "Microsoft Corp", isin: "US5949181045", weight_pct: 1.46, country: "United States", sector: "Information Technology" },
  ],
  ...overrides,
});

describe("InstrumentAllocationPanel (#9974)", () => {
  beforeEach(() => {
    mockGetAllocation.mockReset();
    mockRefresh.mockReset();
  });

  it("shows a fund's countries, sectors and top holdings with its data source", async () => {
    mockGetAllocation.mockResolvedValueOnce(allocation());

    render(<InstrumentAllocationPanel ticker="MINV.L" />);

    const countries = await screen.findByRole("table", { name: "Countries" });
    expect(within(countries).getByText("United States")).toBeInTheDocument();
    expect(within(countries).getByText("66.2%")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Sectors" })).toHaveTextContent("Information Technology");
    const top = screen.getByRole("table", { name: "Top holdings" });
    expect(within(top).getByText("Microsoft Corp")).toBeInTheDocument();
    expect(screen.getByTestId("instrument-allocation-source")).toHaveTextContent(
      "portfolio as of 2026-10-05 (380 holdings)",
    );
    const provenance = screen.getByTestId("instrument-allocation-provenance");
    expect(within(provenance).getByRole("link", { name: "Morningstar" })).toHaveAttribute(
      "href",
      "https://global.morningstar.com/en-gb/search?query=IE00B8FHGS14",
    );
    expect(provenance).toHaveTextContent("last updated 2026-10-07");
    expect(screen.getByText(/top holdings shown make up 1.5%/)).toBeInTheDocument();
    expect(mockGetAllocation).toHaveBeenCalledWith("MINV.L", expect.any(AbortSignal));
  });

  it("explains a single share is all in its own country and sector", async () => {
    mockGetAllocation.mockResolvedValueOnce(
      allocation({
        kind: "security",
        source: null,
        countries: [{ label: "United Kingdom", weight_pct: 100 }],
        sectors: [{ label: "Health Care", weight_pct: 100 }],
        top_holdings: [{ name: "GSK plc", isin: "GB00BN7SWP63", weight_pct: 100 }],
      }),
    );

    render(<InstrumentAllocationPanel ticker="GSK.L" />);

    expect(await screen.findByTestId("instrument-allocation-source")).toHaveTextContent("A single company");
    expect(screen.getByRole("table", { name: "Countries" })).toHaveTextContent("United Kingdom100.0%");
    expect(screen.queryByText(/top holdings shown make up/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Refresh" })).not.toBeInTheDocument();
  });

  it("labels hand-entered data and links its source document", async () => {
    mockGetAllocation.mockResolvedValueOnce(
      allocation({
        source: "manual",
        source_url: "https://example.com/factsheet.pdf",
        note: "Derived from valuations.",
      }),
    );

    render(<InstrumentAllocationPanel ticker="SERE.L" />);

    const link = await screen.findByRole("link", { name: "Manual (fund reports)" });
    expect(link).toHaveAttribute("href", "https://example.com/factsheet.pdf");
    expect(screen.getByTestId("instrument-allocation-note")).toHaveTextContent("Derived from valuations.");
  });

  it("refreshes a fund and shows the new data", async () => {
    mockGetAllocation.mockResolvedValueOnce(allocation({ kind: "fund_uncovered", source: null, top_holdings: [] }));
    mockRefresh.mockResolvedValueOnce({ updated: true, allocation: allocation() });

    render(<InstrumentAllocationPanel ticker="MINV.L" />);
    fireEvent.click(await screen.findByRole("button", { name: "Refresh" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Updated from Morningstar.");
    expect(mockRefresh).toHaveBeenCalledWith("MINV.L");
    expect(screen.getByRole("table", { name: "Top holdings" })).toHaveTextContent("Microsoft Corp");
  });

  it("says when no source covers the fund", async () => {
    const uncovered = allocation({ kind: "fund_uncovered", source: null, top_holdings: [] });
    mockGetAllocation.mockResolvedValueOnce(uncovered);
    mockRefresh.mockResolvedValueOnce({ updated: false, allocation: uncovered });

    render(<InstrumentAllocationPanel ticker="HICL.L" />);
    fireEvent.click(await screen.findByRole("button", { name: "Refresh" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Neither Morningstar nor justETF");
  });

  it("keeps the current data when a refresh fails", async () => {
    mockGetAllocation.mockResolvedValueOnce(allocation());
    mockRefresh.mockRejectedValueOnce(new Error("HTTP 502"));

    render(<InstrumentAllocationPanel ticker="MINV.L" />);
    fireEvent.click(await screen.findByRole("button", { name: "Refresh" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Refresh failed: HTTP 502");
    expect(screen.getByRole("table", { name: "Countries" })).toHaveTextContent("United States");
    expect(screen.getByRole("button", { name: "Refresh" })).not.toBeDisabled();
  });

  it("says when a fund has no look-through data", async () => {
    mockGetAllocation.mockResolvedValueOnce(
      allocation({ kind: "fund_uncovered", source: null, top_holdings: [] }),
    );

    render(<InstrumentAllocationPanel ticker="HICL.L" />);

    expect(await screen.findByTestId("instrument-allocation-source")).toHaveTextContent(
      "No look-through data for this fund yet",
    );
    expect(screen.queryByRole("table", { name: "Top holdings" })).not.toBeInTheDocument();
  });

  it("shows a load error", async () => {
    mockGetAllocation.mockRejectedValueOnce(new Error("allocation boom"));

    render(<InstrumentAllocationPanel ticker="MINV.L" />);

    expect(await screen.findByText("allocation boom")).toBeInTheDocument();
  });
});

describe("LookThroughCoverageNote (#9974)", () => {
  it("omits the not-covered warning when every fund is looked through", () => {
    render(
      <MemoryRouter>
        <LookThroughCoverageNote
          format={(v) => `£${v}`}
          coverage={{
            looked_through_value_gbp: 500,
            direct_value_gbp: 0,
            not_covered_value_gbp: 0,
            cash_value_gbp: 0,
            funds: [{ ticker: "VWRL.L", name: "All-World", value_gbp: 500, as_of: "2026-08-31" }],
            not_covered: [],
          }}
        />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("look-through-coverage")).toHaveTextContent("1 funds (£500) looked through");
    expect(screen.queryByTestId("look-through-not-covered")).not.toBeInTheDocument();
  });
});

describe("foldWeightRows (#9974)", () => {
  it("keeps short lists and folds a long tail into one row", () => {
    const short = [{ label: "A", weight_pct: 100 }];
    expect(foldWeightRows(short, () => "Other")).toBe(short);

    const long = Array.from({ length: 20 }, (_, i) => ({ label: `C${i}`, weight_pct: 5 }));
    const folded = foldWeightRows(long, (n) => `Other (${n} more)`);
    expect(folded).toHaveLength(15);
    expect(folded[14]).toEqual({ label: "Other (6 more)", weight_pct: 30 });
  });
});
