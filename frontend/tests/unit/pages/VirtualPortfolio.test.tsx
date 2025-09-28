import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, describe, it, expect, vi } from "vitest";
import VirtualPortfolio from "@/pages/VirtualPortfolio";
import * as api from "@/api";
import type { OwnerSummary, VirtualPortfolio as VirtualPortfolioType } from "@/types";

vi.mock("@/api");

const mockGetVirtualPortfolios = vi.mocked(api.getVirtualPortfolios);
const mockGetOwners = vi.mocked(api.getOwners);
const mockGetVirtualPortfolio = vi.mocked(api.getVirtualPortfolio);

describe("VirtualPortfolio page", () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

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
      { owner: "bob", full_name: "Bob Example", accounts: ["A1"] } as OwnerSummary,
    ]);
    mockGetVirtualPortfolio.mockResolvedValueOnce({
      id: 1,
      name: "Test VP",
      accounts: ["bob:A1"],
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
    mockGetVirtualPortfolios.mockRejectedValue(new Error("fail"));
    mockGetOwners.mockResolvedValue([]);

    render(<VirtualPortfolio />);

    expect(
      await screen.findByText(
        /Unable to load virtual portfolios\. Please try again\./i,
        undefined,
        { timeout: 6000 },
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/Loading\.\.\./i)).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: /Retry/i }, { timeout: 6000 }),
    ).toBeInTheDocument();
  });

  it("allows retrying the initial load after failures", async () => {
    mockGetVirtualPortfolios
      .mockRejectedValueOnce(new Error("fail"))
      .mockRejectedValueOnce(new Error("fail again"))
      .mockRejectedValueOnce(new Error("still failing"))
      .mockResolvedValueOnce([
        {
          id: 2,
          name: "Recovered VP",
          accounts: [],
          holdings: [],
        } as VirtualPortfolioType,
      ]);
    mockGetOwners.mockResolvedValue([]);

    render(<VirtualPortfolio />);

    const retryButton = await screen.findByRole(
      "button",
      { name: /Retry/i },
      { timeout: 6000 },
    );

    mockGetOwners.mockResolvedValueOnce([
      { owner: "bob", full_name: "Bob Example", accounts: ["A1"] } as OwnerSummary,
    ]);

    fireEvent.click(retryButton);

    expect(
      await screen.findByRole("option", { name: "Recovered VP" }),
    ).toBeInTheDocument();
  });
});
