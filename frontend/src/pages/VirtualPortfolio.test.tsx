import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import VirtualPortfolio from "./VirtualPortfolio";
import * as api from "../api";

vi.mock("../api");

const mockGetVirtualPortfolios = vi.mocked(api.getVirtualPortfolios);
const mockGetOwners = vi.mocked(api.getOwners);
const mockGetVirtualPortfolio = vi.mocked(api.getVirtualPortfolio);

describe("VirtualPortfolio page", () => {
  it("loads portfolios and allows selecting one", async () => {
    mockGetVirtualPortfolios.mockResolvedValueOnce([
      { id: 1, name: "Test VP" } as any,
    ]);
    mockGetOwners.mockResolvedValueOnce([
      { owner: "Bob", accounts: ["A1"] } as any,
    ]);
    mockGetVirtualPortfolio.mockResolvedValueOnce({
      id: 1,
      name: "Test VP",
      accounts: ["Bob:A1"],
      holdings: [],
    } as any);

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
});
