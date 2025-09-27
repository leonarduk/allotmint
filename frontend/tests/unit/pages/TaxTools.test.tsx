import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TaxTools from "@/pages/TaxTools";
import { getAllowances, getPortfolio, harvestTax } from "@/api";
import { useRoute } from "@/RouteContext";

vi.mock("@/api", () => ({
  harvestTax: vi.fn(),
  getAllowances: vi.fn(),
  getPortfolio: vi.fn(),
}));

vi.mock("@/RouteContext", () => ({
  useRoute: vi.fn(),
}));

describe("TaxTools", () => {
  const allowancesMock = getAllowances as unknown as vi.Mock;
  const harvestMock = harvestTax as unknown as vi.Mock;
  const portfolioMock = getPortfolio as unknown as vi.Mock;
  const useRouteMock = useRoute as unknown as vi.Mock;

  const basePortfolio = {
    owner: "demo",
    as_of: "2024-01-01",
    trades_this_month: 0,
    trades_remaining: 10,
    total_value_estimate_gbp: 15000,
    accounts: [
      {
        account_type: "isa",
        currency: "GBP",
        value_estimate_gbp: 15000,
        holdings: [
          {
            ticker: "ABC",
            name: "ABC Corp",
            units: 10,
            cost_basis_gbp: 1000,
            market_value_gbp: 600,
            current_price_gbp: 60,
          },
          {
            ticker: "XYZ",
            name: "XYZ Ltd",
            units: 5,
            effective_cost_basis_gbp: 500,
            market_value_gbp: 250,
            current_price_gbp: 50,
          },
        ],
      },
    ],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    allowancesMock.mockResolvedValue({
      owner: "demo",
      tax_year: "2024",
      allowances: {
        isa: { used: 1000, limit: 20000, remaining: 19000 },
      },
    });
    harvestMock.mockResolvedValue({ trades: [] });
    portfolioMock.mockResolvedValue(basePortfolio);
    useRouteMock.mockReturnValue({
      mode: "owner",
      setMode: vi.fn(),
      selectedOwner: "demo",
      setSelectedOwner: vi.fn(),
      selectedGroup: "",
      setSelectedGroup: vi.fn(),
    });
  });

  it("loads holdings for the active owner", async () => {
    render(<TaxTools />);

    await screen.findByTestId("harvest-candidates");

    expect(portfolioMock).toHaveBeenCalledWith("demo");
    expect(screen.getByText("ABC Corp")).toBeInTheDocument();
    expect(screen.getByLabelText(/Select XYZ/)).toBeInTheDocument();
  });

  it("disables button and shows spinner while loading", async () => {
    let resolvePromise: (value: { trades: any[] }) => void;
    harvestMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePromise = resolve;
        }),
    );

    render(<TaxTools />);

    await screen.findByTestId("harvest-candidates");

    const button = screen.getByRole("button", { name: /run harvest/i });
    fireEvent.click(button);

    await screen.findByTestId("spinner");
    expect(button).toBeDisabled();

    resolvePromise!({ trades: [{ ticker: "ABC", loss: 400 }] });
    await screen.findByTestId("harvest-results");
  });

  it("allows selecting candidates and runs harvest", async () => {
    harvestMock.mockResolvedValue({
      trades: [
        { ticker: "ABC", loss: 400 },
        { ticker: "XYZ", loss: 250 },
      ],
    });

    render(<TaxTools />);

    await screen.findByTestId("harvest-candidates");

    fireEvent.click(screen.getByLabelText(/Select XYZ/));
    const threshold = screen.getByLabelText(/Loss threshold/);
    fireEvent.change(threshold, { target: { value: "10" } });

    fireEvent.click(screen.getByRole("button", { name: /run harvest/i }));

    await screen.findByText(/Total realized loss/i);

    expect(harvestMock).toHaveBeenCalledWith(
      [
        { ticker: "ABC", basis: 100, price: 60 },
        { ticker: "XYZ", basis: 100, price: 50 },
      ],
      10,
    );
    expect(screen.getByTestId("harvest-results")).toHaveTextContent("XYZ");
  });

  it("supports manual advanced entries", async () => {
    harvestMock.mockResolvedValue({ trades: [{ ticker: "MAN", loss: 150 }] });

    render(<TaxTools />);

    await screen.findByTestId("harvest-candidates");

    fireEvent.click(screen.getByLabelText(/Select ABC/));

    fireEvent.click(screen.getByRole("button", { name: /advanced/i }));

    const advanced = await screen.findByTestId("advanced-form");
    fireEvent.change(within(advanced).getByPlaceholderText(/ticker/i), {
      target: { value: "MAN" },
    });
    fireEvent.change(within(advanced).getByPlaceholderText(/basis per unit/i), {
      target: { value: "95" },
    });
    fireEvent.change(within(advanced).getByPlaceholderText(/price/i), {
      target: { value: "80" },
    });

    fireEvent.click(screen.getByRole("button", { name: /run harvest/i }));

    await screen.findByTestId("harvest-results");

    expect(harvestMock).toHaveBeenCalledWith(
      [{ ticker: "MAN", basis: 95, price: 80 }],
      0,
    );
  });

  it("renders allowance data", async () => {
    render(<TaxTools />);

    await waitFor(() => expect(screen.getAllByText(/isa/i).length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getAllByText("19000.00").length).toBeGreaterThan(0));
  });
});
