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
    fireEvent.click(screen.getByRole("button", { name: /run harvest/i }));
    await screen.findByText(/ABC/);
    expect(mock).toHaveBeenCalled();
  });
});
