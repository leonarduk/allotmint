import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { OwnerPortfolioActions } from "@/components/OwnerPortfolioActions";
import { AuthContext } from "@/AuthContext";
import { complianceForOwner } from "@/api";

vi.mock("@/api", () => ({
  complianceForOwner: vi.fn().mockResolvedValue({ warnings: [] }),
  getValueAtRisk: vi.fn(),
  recomputeValueAtRisk: vi.fn(),
  getVarBreakdown: vi.fn(),
}));

const accounts = [
  { account_type: "isa", currency: "GBP", holdings: [] },
] as unknown as import("@/types").Account[];

const baseProps = {
  owner: "alice",
  asOf: "2026-01-01",
  accounts,
  activeAccountType: null,
  onDateChange: vi.fn(),
  onMutated: vi.fn(),
};

describe("OwnerPortfolioActions", () => {
  beforeEach(() => {
    vi.mocked(complianceForOwner).mockClear();
  });

  // Issue #7411: the portfolio action bar is the primary entry point for
  // "Add holding" / "Import CSV" / "Add account" — these must disable
  // themselves for a demo-scoped session.
  it("disables the mutating action buttons when demoReadOnly is true", () => {
    render(
      <AuthContext.Provider
        value={{
          user: null,
          setUser: vi.fn(),
          logout: null,
          setLogout: vi.fn(),
          demoReadOnly: true,
          setDemoReadOnly: vi.fn(),
        }}
      >
        <OwnerPortfolioActions {...baseProps} />
      </AuthContext.Provider>,
    );

    const addPosition = screen.getByRole("button", { name: /add position/i });
    const importCsv = screen.getByRole("button", { name: /import csv/i });
    const addAccount = screen.getByRole("button", { name: /add account/i });

    expect(addPosition).toBeDisabled();
    expect(importCsv).toBeDisabled();
    expect(addAccount).toBeDisabled();
    expect(addPosition).toHaveAttribute("title");
    expect(importCsv).toHaveAttribute("title");
    expect(addAccount).toHaveAttribute("title");
  });

  it("leaves the action buttons enabled for an ordinary signed-in session", () => {
    render(<OwnerPortfolioActions {...baseProps} />);

    expect(screen.getByRole("button", { name: /add position/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /import csv/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /add account/i })).toBeEnabled();
  });
});
