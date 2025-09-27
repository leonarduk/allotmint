import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TaxTools from "@/pages/TaxTools";
import { getAllowances, harvestTax } from "@/api";
import { useRoute } from "@/RouteContext";

vi.mock("@/api", () => ({
  harvestTax: vi.fn(),
  getAllowances: vi.fn(),
}));

vi.mock("@/RouteContext", () => ({
  useRoute: vi.fn(),
}));

describe("TaxTools", () => {
  const allowancesMock = getAllowances as unknown as vi.Mock;
  const harvestMock = harvestTax as unknown as vi.Mock;
  const useRouteMock = useRoute as unknown as vi.Mock;

  beforeEach(() => {
    vi.clearAllMocks();
    useRouteMock.mockReturnValue({
      mode: "taxtools",
      setMode: vi.fn(),
      selectedOwner: "demo",
      setSelectedOwner: vi.fn(),
      selectedGroup: "",
      setSelectedGroup: vi.fn(),
    });
    allowancesMock.mockResolvedValue({
      owner: "demo",
      tax_year: "2024",
      allowances: {
        isa: { used: 1000, limit: 20000, remaining: 19000 },
      },
    });
    harvestMock.mockResolvedValue({ trades: [] });
  });

  it("calls harvest API and shows results", async () => {
    harvestMock.mockResolvedValue({ trades: [{ ticker: "ABC", loss: 123 }] });

    render(<TaxTools />);

    fireEvent.change(screen.getByPlaceholderText(/ticker/i), {
      target: { value: "ABC" },
    });
    fireEvent.change(screen.getByPlaceholderText(/basis/i), {
      target: { value: "100" },
    });
    fireEvent.change(screen.getByPlaceholderText(/price/i), {
      target: { value: "80" },
    });
    fireEvent.change(screen.getByPlaceholderText(/threshold/i), {
      target: { value: "0" },
    });

    fireEvent.click(screen.getByRole("button", { name: /run harvest/i }));

    await screen.findByText(/ABC/);

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

    fireEvent.change(screen.getByPlaceholderText(/ticker/i), {
      target: { value: "XYZ" },
    });
    fireEvent.change(screen.getByPlaceholderText(/basis/i), {
      target: { value: "200" },
    });
    fireEvent.change(screen.getByPlaceholderText(/price/i), {
      target: { value: "150" },
    });
    fireEvent.change(screen.getByPlaceholderText(/threshold/i), {
      target: { value: "5" },
    });

    const button = screen.getByRole("button", { name: /run harvest/i });
    fireEvent.click(button);

    await screen.findByTestId("spinner");
    expect(button).toBeDisabled();

    resolvePromise!({ trades: [{ ticker: "XYZ", loss: 50 }] });
    await screen.findByText(/XYZ/);
  });

  it("renders allowance data", async () => {
    render(<TaxTools />);

    await screen.findByText(/tax year 2024/i);
    expect(screen.getByText(/used £1,000.00 of £20,000.00 total/i)).toBeInTheDocument();

    const table = screen.getByRole("table");
    const isaCell = within(table)
      .getAllByRole("cell")
      .find((cell) => cell.textContent?.trim().toLowerCase() === "isa");
    expect(isaCell).toBeDefined();
    const isaRow = isaCell!.closest("tr");
    expect(isaRow).not.toBeNull();
    expect(isaRow).toHaveTextContent("£20,000.00");
    expect(isaRow).toHaveTextContent("£19,000.00");
    expect(allowancesMock).toHaveBeenCalledWith("demo");
  });

  it("highlights usage when over the allowance", async () => {
    allowancesMock.mockResolvedValue({
      owner: "demo",
      tax_year: "2024",
      allowances: {
        isa: { used: 21000, limit: 20000, remaining: -1000 },
      },
    });

    render(<TaxTools />);

    const table = await screen.findByRole("table");
    const isaCell = within(table)
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

    render(<TaxTools />);

    expect(
      await screen.findByText(/choose a portfolio owner to see their allowance usage/i),
    ).toBeInTheDocument();
    expect(allowancesMock).not.toHaveBeenCalled();
  });

  it("shows validation error when inputs are incomplete", async () => {
    render(<TaxTools />);

    fireEvent.change(screen.getByPlaceholderText(/ticker/i), {
      target: { value: "ABC" },
    });
    fireEvent.click(screen.getByRole("button", { name: /run harvest/i }));

    await screen.findByText(/fill out all fields/i);
    expect(harvestMock).not.toHaveBeenCalled();
  });
});
