import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import TaxAllowances from "./TaxAllowances";
import { getAllowances } from "../api";

vi.mock("../api", () => ({
  getAllowances: vi.fn(),
}));

describe("TaxAllowances", () => {
  it("renders allowance data", async () => {
    const mock = getAllowances as unknown as vi.Mock;
    mock.mockResolvedValue({
      owner: "demo",
      tax_year: "2024",
      allowances: { isa: { used: 1000, limit: 20000, remaining: 19000 } },
    });
    render(<TaxAllowances />);
    expect(mock).toHaveBeenCalled();
    await screen.findByText(/isa/i);
    await screen.findByText("19000.00");
  });
});
