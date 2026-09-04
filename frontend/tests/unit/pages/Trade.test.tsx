import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import Trade from "@/pages/Trade";
import { validateTrade } from "@/api";
import type { ComplianceResult } from "@/types";

vi.mock("@/api", () => ({
  validateTrade: vi.fn(),
}));

function buildResult(overrides: Partial<ComplianceResult> = {}): ComplianceResult {
  return {
    owner: "owner1",
    warnings: [],
    trade_counts: {},
    ...overrides,
  };
}

describe("Trade page", () => {
  beforeEach(() => {
    vi.mocked(validateTrade).mockReset();
  });

  it("renders returned warnings as a list and does not show 'Trade valid'", async () => {
    vi.mocked(validateTrade).mockResolvedValue(
      buildResult({ warnings: ["Exceeds monthly trade limit", "Ticker not found"] }),
    );

    render(<Trade />);

    fireEvent.click(screen.getByRole("button", { name: /submit trade/i }));

    expect(
      await screen.findByText("Exceeds monthly trade limit"),
    ).toBeInTheDocument();
    expect(screen.getByText("Ticker not found")).toBeInTheDocument();

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);

    expect(screen.queryByText("Trade valid")).not.toBeInTheDocument();
  });

  it("shows 'Trade valid' and no warning list when validation returns no warnings", async () => {
    vi.mocked(validateTrade).mockResolvedValue(buildResult({ warnings: [] }));

    render(<Trade />);

    fireEvent.click(screen.getByRole("button", { name: /submit trade/i }));

    expect(await screen.findByText("Trade valid")).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it("renders the thrown error via String(err) and does not show 'Trade valid'", async () => {
    vi.mocked(validateTrade).mockRejectedValue(new Error("network down"));

    render(<Trade />);

    fireEvent.click(screen.getByRole("button", { name: /submit trade/i }));

    expect(await screen.findByText("Error: network down")).toBeInTheDocument();
    expect(screen.queryByText("Trade valid")).not.toBeInTheDocument();
  });

  it("updates the controlled ticker input as the user types", () => {
    render(<Trade />);

    const tickerInput = screen.getByLabelText(/ticker/i) as HTMLInputElement;
    expect(tickerInput.value).toBe("");

    fireEvent.change(tickerInput, { target: { value: "AAPL" } });

    expect(tickerInput.value).toBe("AAPL");
  });
});
