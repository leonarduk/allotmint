import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGetOwners = vi.hoisted(() => vi.fn());
const mockGetPortfolio = vi.hoisted(() => vi.fn());
const mockGetRebalance = vi.hoisted(() => vi.fn());

vi.mock("@/api", () => ({
  getOwners: mockGetOwners,
  getPortfolio: mockGetPortfolio,
  getRebalance: mockGetRebalance,
}));

vi.mock("@/RouteContext", () => ({
  useRoute: () => ({
    mode: "rebalance",
    setMode: vi.fn(),
    selectedOwner: "",
    setSelectedOwner: vi.fn(),
    selectedGroup: "",
    setSelectedGroup: vi.fn(),
  }),
}));

describe("Rebalance page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
    mockGetPortfolio.mockResolvedValue({
      accounts: [
        {
          holdings: [
            { ticker: "AAA", market_value_gbp: 50 },
            { ticker: "BBB", market_value_gbp: 50 },
          ],
        },
      ],
    });
  });

  it("shows current/target weight percentages and explains trade value units", async () => {
    mockGetRebalance.mockResolvedValue([
      { ticker: "AAA", action: "buy", amount: 10 },
      { ticker: "BBB", action: "sell", amount: 10 },
    ]);

    const { default: Rebalance } = await import("@/pages/Rebalance");
    render(<Rebalance />);

    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledWith("alex"));

    fireEvent.click(screen.getByRole("button", { name: /rebalance/i }));

    expect(await screen.findByRole("columnheader", { name: /current weight/i })).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader", { name: /target weight/i }).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("columnheader", { name: /trade value/i })).toBeInTheDocument();
    expect(screen.getAllByText("50.00%")).toHaveLength(4);
    expect(
      screen.getByText(/Trade value is the amount of portfolio value/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/not number of units\/shares/i)).toBeInTheDocument();
  });
});
