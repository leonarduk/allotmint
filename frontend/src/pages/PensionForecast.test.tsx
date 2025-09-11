import "../setupTests";
import { render, screen, within, fireEvent, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, afterEach } from "vitest";

const mockGetOwners = vi.hoisted(() => vi.fn());
const mockGetPensionForecast = vi.hoisted(() => vi.fn());

vi.mock("../api", () => ({
  getOwners: mockGetOwners,
  getPensionForecast: mockGetPensionForecast,
}));

describe("PensionForecast page", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders owner selector", async () => {
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 0,
      pension_pot_gbp: 0,
      current_age: 30,
      retirement_age: 65,
      dob: "1990-01-01",
    });

    const { default: PensionForecast } = await import("./PensionForecast");

    render(<PensionForecast />);

    const form = document.querySelector("form")!;
    const ownerSelect = await within(form).findByLabelText(/owner/i);
    expect(ownerSelect).toBeInTheDocument();
  });

  it("submits with selected owner", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", accounts: [] },
      { owner: "beth", accounts: [] },
    ]);
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 0,
      pension_pot_gbp: 123,
      current_age: 30,
      retirement_age: 65,
      dob: "1990-01-01",
    });

    const { default: PensionForecast } = await import("./PensionForecast");

    render(<PensionForecast />);

    await screen.findByText("beth");
    const ownerSelects = await screen.findAllByLabelText(/owner/i);
    const ownerSelect = ownerSelects[ownerSelects.length - 1];
    await userEvent.selectOptions(ownerSelect, "beth");

    const growth = screen.getByLabelText(/growth assumption/i);
    await userEvent.selectOptions(growth, "7");

    const monthly = screen.getByLabelText(/monthly contribution/i);
    fireEvent.change(monthly, { target: { value: "100" } });

    const btn = screen.getByRole("button", { name: /forecast/i });
    await userEvent.click(btn);

    await vi.waitFor(() =>
      expect(mockGetPensionForecast).toHaveBeenCalledWith(
        expect.objectContaining({
          owner: "beth",
          investmentGrowthPct: 7,
          contributionMonthly: 100,
        }),
      ),
    );
    await screen.findByText(/birth date: 1990-01-01/i);
    await screen.findByText(/pension pot: £123.00/i);
  });
});

