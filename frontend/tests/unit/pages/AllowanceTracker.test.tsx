import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import AllowanceTracker from "@/pages/AllowanceTracker";
import * as api from "@/api";

vi.mock("@/api");
const mockGetAllowances = vi.mocked(api.getAllowances);

describe("AllowanceTracker page", () => {
  it("shows an accessible skeleton while loading, then the table", async () => {
    mockGetAllowances.mockReturnValue(new Promise(() => {}));
    render(<AllowanceTracker />);

    expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("renders the allowance table once data resolves", async () => {
    mockGetAllowances.mockResolvedValue({
      allowances: {
        isa: { used: 1000, limit: 20000, remaining: 19000 },
      },
    });

    render(<AllowanceTracker />);

    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(screen.getByText("isa")).toBeInTheDocument();
    expect(screen.queryByRole("status", { name: /loading/i })).not.toBeInTheDocument();
  });
});
