import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";

vi.mock("../api", () => ({
  getOwners: vi.fn(),
  complianceForOwner: vi.fn(),
}));

import ComplianceWarnings from "./ComplianceWarnings";
import { getOwners, complianceForOwner } from "../api";
import type { OwnerSummary, ComplianceResult } from "../types";

describe("ComplianceWarnings page", () => {
  it("renders hold countdowns", async () => {
    (getOwners as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([
      { owner: "alice", accounts: [] } as OwnerSummary,
    ]);
    const result: ComplianceResult = {
      owner: "alice",
      warnings: [],
      trade_counts: { "2024-01": 1 },
      hold_countdowns: { AAA: 5 },
      trades_remaining: 4,
      trades_this_month: 1,
    };
    (complianceForOwner as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(result);

    render(
      <MemoryRouter initialEntries={["/compliance/alice"]}>
        <Routes>
          <Route path="/compliance/:owner" element={<ComplianceWarnings />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText(/AAA: 5 days?/i)).toBeInTheDocument();
  });
});

