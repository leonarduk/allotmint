import { render, screen, fireEvent } from "@testing-library/react";
import { vi } from "vitest";
import TaxHarvest from "./TaxHarvest";
import { harvestTax } from "../api";

vi.mock("../api", () => ({
  harvestTax: vi.fn(),
}));

describe("TaxHarvest", () => {
  it("calls API and shows results", async () => {
    const mock = harvestTax as unknown as vi.Mock;
    mock.mockResolvedValue({ trades: [{ ticker: "ABC" }] });
    render(<TaxHarvest />);
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
    expect(mock).toHaveBeenCalledWith(
      [{ ticker: "ABC", basis: 100, price: 80 }],
      0
    );
  });
});
