import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import PortfolioPage from "./Portfolio.tsx";
import type { Portfolio } from "../types";
import * as api from "../api";

vi.mock("../api");
const mockGetPortfolio = vi.mocked(api.getPortfolio);

describe("Portfolio page", () => {
  it("fetches and displays portfolio data", async () => {
    mockGetPortfolio.mockResolvedValueOnce({
      owner: "alice",
      as_of: "2024-01-01",
      trades_this_month: 0,
      trades_remaining: 0,
      total_value_estimate_gbp: 0,
      accounts: [],
    } as Portfolio);
    render(<PortfolioPage />);
    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledWith("alice"));
    expect(await screen.findByTestId("owner-name")).toHaveTextContent("alice");
  });
});
