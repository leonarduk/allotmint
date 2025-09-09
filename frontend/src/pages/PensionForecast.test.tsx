import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockGetOwners = vi.hoisted(() => vi.fn());
const mockGetPensionForecast = vi.hoisted(() => vi.fn());

vi.mock("../api", () => ({
  getOwners: mockGetOwners,
  getPensionForecast: mockGetPensionForecast,
}));

describe("PensionForecast page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders owner selector", async () => {
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 0,
      current_age: 30,
      retirement_age: 65,
    });

    const { default: PensionForecast } = await import("./PensionForecast");

    render(<PensionForecast />);

    const select = await screen.findByLabelText(/owner/i);
    expect(select).toBeInTheDocument();
  });

  it("submits with selected owner", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", accounts: [] },
      { owner: "beth", accounts: [] },
    ]);
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 0,
      current_age: 30,
      retirement_age: 65,
    });

    const { default: PensionForecast } = await import("./PensionForecast");

    render(<PensionForecast />);

    const select = await screen.findByLabelText(/owner/i);
    fireEvent.change(select, { target: { value: "beth" } });

    const btn = screen.getByRole("button", { name: /forecast/i });
    fireEvent.click(btn);

    await vi.waitFor(() =>
      expect(mockGetPensionForecast).toHaveBeenCalledWith(
        expect.objectContaining({ owner: "beth" }),
      ),
    );
  });
});

