import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("../api", () => ({
  getVirtualPortfolios: vi.fn().mockResolvedValue([]),
  getVirtualPortfolio: vi.fn(),
  createVirtualPortfolio: vi.fn(),
  updateVirtualPortfolio: vi.fn(),
  deleteVirtualPortfolio: vi.fn(),
  getOwners: vi.fn().mockResolvedValue([]),
}));

import VirtualPortfolio from "./VirtualPortfolio";

describe("VirtualPortfolio page", () => {
  it("renders heading", async () => {
    render(<VirtualPortfolio />);
    expect(await screen.findByText(/Virtual Portfolios/)).toBeInTheDocument();
  });
});
