import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import VirtualPortfolio from "@/pages/VirtualPortfolio";
import * as api from "@/api";
import type { OwnerSummary, VirtualPortfolio as VirtualPortfolioType } from "@/types";

vi.mock("@/api");

const mockGetVirtualPortfolios = vi.mocked(api.getVirtualPortfolios);
const mockGetOwners = vi.mocked(api.getOwners);
const mockGetVirtualPortfolio = vi.mocked(api.getVirtualPortfolio);

describe("VirtualPortfolio page", () => {
  it("loads portfolios and allows selecting one", async () => {
    mockGetVirtualPortfolios.mockResolvedValueOnce([
      {
        id: 1,
        name: "Test VP",
        accounts: [],
        holdings: [],
      } as VirtualPortfolioType,
    ]);
    mockGetOwners.mockResolvedValueOnce([
      { owner: "Bob", accounts: ["A1"] } as OwnerSummary,
    ]);
    mockGetVirtualPortfolio.mockResolvedValueOnce({
      id: 1,
      name: "Test VP",
      accounts: ["Bob:A1"],
      holdings: [],
    } as VirtualPortfolioType);

    render(<VirtualPortfolio />);

    // Wait for portfolios to load
    expect(await screen.findByRole("option", { name: "Test VP" })).toBeInTheDocument();

    // Select the portfolio
    fireEvent.change(screen.getByLabelText(/Select/i), { target: { value: "1" } });

    await waitFor(() => expect(mockGetVirtualPortfolio).toHaveBeenCalledWith(1));

    expect(screen.getByLabelText(/Name/i)).toHaveValue("Test VP");
    const accountCheckbox = screen.getByLabelText("A1") as HTMLInputElement;
    expect(accountCheckbox.checked).toBe(true);
  });

  it("shows error when loading portfolios fails", async () => {
    mockGetVirtualPortfolios.mockRejectedValueOnce(new Error("fail"));
    mockGetOwners.mockResolvedValueOnce([]);

    render(<VirtualPortfolio />);

    expect(
      await screen.findByText(/Request timed out\. Please try again\./i),
    ).toBeInTheDocument();
  });
});
