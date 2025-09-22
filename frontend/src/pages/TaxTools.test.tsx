import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TaxTools from "./TaxTools";
import { getAllowances, harvestTax } from "../api";

vi.mock("../api", () => ({
  harvestTax: vi.fn(),
  getAllowances: vi.fn(),
}));

describe("TaxTools", () => {
  const allowancesMock = getAllowances as unknown as vi.Mock;
  const harvestMock = harvestTax as unknown as vi.Mock;

  beforeEach(() => {
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

    await screen.findByText(/isa/i);
    await screen.findByText("19000.00");
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
