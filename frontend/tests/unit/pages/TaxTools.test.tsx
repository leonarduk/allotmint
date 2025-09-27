import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TaxTools from "@/pages/TaxTools";
import { getAllowances, getOwners, getPortfolio, harvestTax } from "@/api";
import { useRoute } from "@/RouteContext";

vi.mock("@/api", () => ({
  harvestTax: vi.fn(),
  getAllowances: vi.fn(),
  getOwners: vi.fn(),
  getPortfolio: vi.fn(),
}));

vi.mock("@/RouteContext", () => ({
  useRoute: vi.fn(),
}));

describe("TaxTools", () => {
  const allowancesMock = getAllowances as unknown as vi.Mock;
  const harvestMock = harvestTax as unknown as vi.Mock;
  const ownersMock = getOwners as unknown as vi.Mock;
  const portfolioMock = getPortfolio as unknown as vi.Mock;
  const useRouteMock = useRoute as unknown as vi.Mock;

  beforeEach(() => {
    vi.clearAllMocks();
    useRouteMock.mockReturnValue({
      mode: "taxtools",
      setMode: vi.fn(),
      selectedOwner: "alice",
      setSelectedOwner: vi.fn(),
      selectedGroup: "",
      setSelectedGroup: vi.fn(),
    });
    ownersMock.mockResolvedValue([
      { owner: "alice", accounts: ["isa"] },
      { owner: "bob", accounts: ["gpp"] },
    ]);
    allowancesMock.mockResolvedValue({
      owner: "alice",
      tax_year: "2024",
      allowances: {
        isa: { used: 1000, limit: 20000, remaining: 19000 },
      },
    });
    portfolioMock.mockResolvedValue({
      owner: "alice",
      as_of: "2024-01-01",
      trades_this_month: 0,
      trades_remaining: 0,
      total_value_estimate_gbp: 0,
      accounts: [
        {
          account_type: "isa",
          currency: "GBP",
          value_estimate_gbp: 0,
          holdings: [
            {
              ticker: "ABC",
              name: "ABC Corp",
              units: 10,
              cost_basis_gbp: 1000,
              market_value_gbp: 800,
              gain_gbp: -200,
              current_price_gbp: 80,
              acquired_date: "2023-01-01",
            },
            {
              ticker: "XYZ",
              name: "XYZ Plc",
              units: 5,
              cost_basis_gbp: 500,
              market_value_gbp: 400,
              gain_gbp: -100,
              current_price_gbp: 80,
              acquired_date: "2023-02-01",
            },
          ],
        },
      ],
    });
    harvestMock.mockResolvedValue({ trades: [] });
  });

  it("loads the owner portfolio when an owner is selected", async () => {
    render(<TaxTools />);

    await screen.findByLabelText(/portfolio owner/i);
    await screen.findByRole("checkbox", { name: /abc/i });

    expect(portfolioMock).toHaveBeenCalledWith("alice");
  });

  it("calls harvest API with selected holdings and shows results", async () => {
    harvestMock.mockResolvedValue({ trades: [{ ticker: "ABC", loss: 123 }] });

    render(<TaxTools />);

    const checkbox = await screen.findByRole("checkbox", { name: /abc/i });
    fireEvent.click(checkbox);

    fireEvent.click(screen.getByRole("button", { name: /run harvest/i }));

    await screen.findByTestId("harvest-results");

    expect(harvestMock).toHaveBeenCalledWith(
      [{ ticker: "ABC", basis: 100, price: 80 }],
      0,
    );
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

    const checkbox = await screen.findByRole("checkbox", { name: /abc/i });
    fireEvent.click(checkbox);

    const button = screen.getByRole("button", { name: /run harvest/i });
    fireEvent.click(button);

    await screen.findByTestId("spinner");
    expect(button).toBeDisabled();

    resolvePromise!({ trades: [{ ticker: "XYZ", loss: 50 }] });
    await screen.findByTestId("harvest-results");
  });

  it("renders allowance data", async () => {
    render(<TaxTools />);

    await screen.findByText(/tax year 2024/i);
    expect(screen.getByText(/used £1,000.00 of £20,000.00 total/i)).toBeInTheDocument();

    const tables = await screen.findAllByRole("table");
    const allowancesTable = tables.find((table) =>
      within(table).queryByText(/usage/i),
    );
    expect(allowancesTable).toBeDefined();
    const isaCell = within(allowancesTable!)
      .getAllByRole("cell")
      .find((cell) => cell.textContent?.trim().toLowerCase() === "isa");
    expect(isaCell).toBeDefined();
    const isaRow = isaCell!.closest("tr");
    expect(isaRow).not.toBeNull();
    expect(isaRow).toHaveTextContent("£20,000.00");
    expect(isaRow).toHaveTextContent("£19,000.00");
    expect(allowancesMock).toHaveBeenCalledWith("alice");
  });

  it("highlights usage when over the allowance", async () => {
    allowancesMock.mockResolvedValue({
      owner: "alice",
      tax_year: "2024",
      allowances: {
        isa: { used: 21000, limit: 20000, remaining: -1000 },
      },
    });

    render(<TaxTools />);

    const tables = await screen.findAllByRole("table");
    const allowancesTable = tables.find((table) =>
      within(table).queryByText(/usage/i),
    );
    expect(allowancesTable).toBeDefined();
    const isaCell = within(allowancesTable!)
      .getAllByRole("cell")
      .find((cell) => cell.textContent?.trim().toLowerCase() === "isa");
    expect(isaCell).toBeDefined();
    const isaRow = isaCell!.closest("tr");
    expect(isaRow).not.toBeNull();

    const usageElements = within(isaRow!).getAllByText(/105%/);
    const visibleUsage = usageElements.find((node) => !node.classList.contains("sr-only"));
    expect(visibleUsage).toHaveClass("text-red-600");
  });

  it("prompts for owner selection when none is set", async () => {
    useRouteMock.mockReturnValue({
      mode: "taxtools",
      setMode: vi.fn(),
      selectedOwner: "",
      setSelectedOwner: vi.fn(),
      selectedGroup: "",
      setSelectedGroup: vi.fn(),
    });
    ownersMock.mockResolvedValue([
      { owner: "alice", accounts: ["isa"] },
      { owner: "bob", accounts: ["gpp"] },
    ]);

    render(<TaxTools />);

    expect(
      await screen.findByText(/choose a portfolio owner to see their allowance usage/i),
    ).toBeInTheDocument();
    expect(allowancesMock).not.toHaveBeenCalled();
  });

  it("allows manual entry through the advanced toggle", async () => {
    render(<TaxTools />);

    const advancedToggle = await screen.findByLabelText(/advanced/i);
    fireEvent.click(advancedToggle);

    fireEvent.change(screen.getByPlaceholderText(/ticker/i), {
      target: { value: "MAN" },
    });
    fireEvent.change(screen.getByPlaceholderText(/basis/i), {
      target: { value: "50" },
    });
    fireEvent.change(screen.getByPlaceholderText(/price/i), {
      target: { value: "40" },
    });

    const slider = screen.getByRole("slider");
    fireEvent.change(slider, { target: { value: "10" } });

    fireEvent.click(screen.getByRole("button", { name: /run harvest/i }));

    expect(harvestMock).toHaveBeenCalledWith(
      [{ ticker: "MAN", basis: 50, price: 40 }],
      10,
    );
  });

  it("shows validation error when no positions are selected", async () => {
    render(<TaxTools />);

    await screen.findByRole("checkbox", { name: /abc/i });

    fireEvent.click(screen.getByRole("button", { name: /run harvest/i }));

    expect(
      await screen.findByText(/select a position or enter one manually/i),
    ).toBeInTheDocument();
    expect(harvestMock).not.toHaveBeenCalled();
  });
});
