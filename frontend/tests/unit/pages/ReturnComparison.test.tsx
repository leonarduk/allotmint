import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockGetReturnComparison = vi.hoisted(() => vi.fn());

vi.mock("@/api", () => ({
  getReturnComparison: mockGetReturnComparison,
}));

import ReturnComparison from "@/pages/ReturnComparison";

function renderPage(initialEntries: string[] = ["/returns/compare?owner=alex"]) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <ReturnComparison />
    </MemoryRouter>,
  );
}

describe("ReturnComparison page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches and renders CAGR and cash APY for the owner in the query string", async () => {
    mockGetReturnComparison.mockResolvedValue({
      owner: "alex",
      cagr: 0.081,
      cash_apy: 0.045,
    });

    renderPage();

    expect(await screen.findByText(/Portfolio CAGR: 8.10%/)).toBeInTheDocument();
    expect(screen.getByText(/Cash APY: 4.50%/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Return Comparison – alex" })).toBeInTheDocument();
    expect(mockGetReturnComparison).toHaveBeenCalledWith("alex", 365);
  });

  it("re-fetches with the selected timeframe's day count", async () => {
    mockGetReturnComparison.mockResolvedValue({
      owner: "alex",
      cagr: 0.05,
      cash_apy: 0.02,
    });

    renderPage();
    await screen.findByText(/Portfolio CAGR: 5.00%/);

    const select = screen.getByLabelText(/Timeframe/i);
    fireEvent.change(select, { target: { value: String(365 * 5) } });

    expect(mockGetReturnComparison).toHaveBeenCalledWith("alex", 365 * 5);
  });

  it("shows N/A placeholders and skips fetching when there is no owner", () => {
    renderPage(["/returns/compare"]);

    // The accessible name trims trailing whitespace even though the DOM
    // text node itself is "Return Comparison – " (owner is an empty string).
    expect(screen.getByRole("heading", { name: "Return Comparison –" })).toBeInTheDocument();
    expect(screen.getByText(/Portfolio CAGR: —/)).toBeInTheDocument();
    expect(screen.getByText(/Cash APY: —/)).toBeInTheDocument();
    expect(mockGetReturnComparison).not.toHaveBeenCalled();
  });

  it("falls back to placeholders when only one side of the comparison is available (partial data)", async () => {
    mockGetReturnComparison.mockResolvedValue({
      owner: "alex",
      cagr: 0.033,
      cash_apy: null,
    });

    renderPage();

    expect(await screen.findByText(/Portfolio CAGR: 3.30%/)).toBeInTheDocument();
    expect(screen.getByText(/Cash APY: —/)).toBeInTheDocument();
  });

  it("clears prior results and shows placeholders when the fetch fails", async () => {
    mockGetReturnComparison.mockRejectedValue(new Error("network error"));

    renderPage();

    expect(await screen.findByText(/Portfolio CAGR: —/)).toBeInTheDocument();
    expect(screen.getByText(/Cash APY: —/)).toBeInTheDocument();
  });
});
