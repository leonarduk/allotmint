import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { VarBreakdownModal } from "@/components/VarBreakdownModal";
import type { VarBreakdown } from "@/types";

const contributions: VarBreakdown[] = [
  {
    ticker: "CASH",
    name: "Cash GBP",
    contribution: 60,
    relative_change_percent: -12.5,
    scenario_amount_gbp: -75,
  },
  {
    ticker: "CASH",
    name: "Cash L",
    contribution: 40,
    relative_change_percent: 8.4,
    scenario_amount_gbp: 20,
  },
];

describe("VarBreakdownModal (#6505)", () => {
  it("renders duplicate-ticker contributions without duplicate-key warnings", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <VarBreakdownModal
        contributions={contributions}
        scenarios={[]}
        varDate="2024-01-02"
        varLossPercent={5}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getAllByText("CASH")).toHaveLength(2);
    expect(screen.getByText("Cash GBP")).toBeInTheDocument();
    expect(screen.getByText("Cash L")).toBeInTheDocument();

    const keyWarnings = errorSpy.mock.calls.filter((args) =>
      String(args[0]).includes("same key"),
    );
    expect(keyWarnings).toEqual([]);
    errorSpy.mockRestore();
  });

  it("renders the scenario list with stable date keys", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <VarBreakdownModal
        contributions={[]}
        scenarios={[
          { date: "2024-01-02", portfolio_return: -0.05, loss_percent: 5.0 },
          { date: "2024-03-15", portfolio_return: -0.03, loss_percent: 3.0 },
        ]}
        varDate="2024-01-02"
        varLossPercent={5}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    // Scenario dates are a stable unique field, so each date renders once.
    expect(screen.getAllByText(/2024-01-02 \(5.00% loss\)/)).toHaveLength(1);
    expect(screen.getByText(/2024-03-15 \(3.00% loss\)/)).toBeInTheDocument();

    const keyWarnings = errorSpy.mock.calls.filter((args) =>
      String(args[0]).includes("same key"),
    );
    expect(keyWarnings).toEqual([]);
    errorSpy.mockRestore();
  });
});
