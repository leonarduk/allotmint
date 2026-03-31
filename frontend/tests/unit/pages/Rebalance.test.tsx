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
            { ticker: "AAA", market_value_gbp: 2 },
            { ticker: "BBB", market_value_gbp: 1 },
          ],
        },
      ],
    });
  });

  it("shows weights in the input table and sends target percentages as fractional weights", async () => {
    mockGetRebalance.mockResolvedValue([
      { ticker: "AAA", action: "buy", amount: 10 },
      { ticker: "BBB", action: "sell", amount: 10 },
    ]);

    const { default: Rebalance } = await import("@/pages/Rebalance");
    render(<Rebalance />);

    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledWith("alex"));

    fireEvent.click(screen.getByRole("button", { name: /rebalance/i }));

    expect(mockGetRebalance).toHaveBeenCalledTimes(1);
    const [actualPayload, targetPayload] = mockGetRebalance.mock.calls[0];
    expect(actualPayload).toEqual({ AAA: 2, BBB: 1 });
    expect(targetPayload.AAA + targetPayload.BBB).toBeCloseTo(1, 10);
    expect(targetPayload.AAA).toBeCloseTo(2 / 3, 10);
    expect(targetPayload.BBB).toBeCloseTo(1 / 3, 10);

    expect(await screen.findByRole("columnheader", { name: /current weight/i })).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader", { name: /target weight/i }).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("columnheader", { name: /trade value/i })).toBeInTheDocument();
    expect(screen.getByDisplayValue("66.67%")).toHaveAttribute("readonly");
    expect(screen.getByDisplayValue("33.33%")).toHaveAttribute("readonly");
    expect(
      screen.getByText(/Trade value is the amount of portfolio value/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/not number of units\/shares/i)).toBeInTheDocument();
    expect(screen.getByText(/treated as no-change/i)).toBeInTheDocument();
  });
});
