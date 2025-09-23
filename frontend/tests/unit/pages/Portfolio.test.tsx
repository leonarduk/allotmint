import { render, screen, waitFor, act } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { HelmetProvider } from "react-helmet-async";
import { describe, it, expect, vi } from "vitest";
import PortfolioPage from "@/pages/Portfolio";
import type { Portfolio } from "@/types";
import * as api from "@/api";

vi.mock("@/api");
const mockGetPortfolio = vi.mocked(api.getPortfolio);

describe("Portfolio page", () => {
  it("fetches portfolio whenever owner changes", async () => {
    const router = createMemoryRouter(
      [
        {
          path: "/portfolio/:owner",
          element: <PortfolioPage />,
        },
      ],
      { initialEntries: ["/portfolio/alice"] },
    );

    mockGetPortfolio.mockResolvedValueOnce({
      owner: "alice",
      as_of: "2024-01-01",
      trades_this_month: 0,
      trades_remaining: 0,
      total_value_estimate_gbp: 0,
      accounts: [],
    } as Portfolio);
    render(
      <HelmetProvider>
        <RouterProvider router={router} />
      </HelmetProvider>,
    );

    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledWith("alice"));
    await screen.findByText(/Approx Total:/);

    mockGetPortfolio.mockClear();
    mockGetPortfolio.mockResolvedValueOnce({
      owner: "bob",
      as_of: "2024-01-01",
      trades_this_month: 0,
      trades_remaining: 0,
      total_value_estimate_gbp: 0,
      accounts: [],
    } as Portfolio);

    await act(async () => {
      await router.navigate("/portfolio/bob");
    });

    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledWith("bob"));
    await screen.findByText(/Approx Total:/);
  });
});
