import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PerformanceDiagnostics from "@/pages/PerformanceDiagnostics";

const mockGetPerformance = vi.hoisted(() => vi.fn());
const mockGetPortfolioHoldings = vi.hoisted(() => vi.fn());

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    getPerformance: mockGetPerformance,
    getPortfolioHoldings: mockGetPortfolioHoldings,
  };
});

vi.mock("@/components/Menu", () => ({
  default: ({ selectedOwner }: { selectedOwner?: string }) => (
    <nav data-testid="diagnostics-menu">Menu for {selectedOwner}</nav>
  ),
}));

describe("PerformanceDiagnostics page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetPerformance.mockResolvedValue({
      history: [{ date: "2026-01-01", drawdown: 0 }],
      dataQualityIssues: [],
    });
    mockGetPortfolioHoldings.mockResolvedValue({ holdings: [] });
  });

  it("renders the shared menu with owner context", async () => {
    render(
      <MemoryRouter initialEntries={["/performance/alex/diagnostics"]}>
        <Routes>
          <Route
            path="/performance/:owner/diagnostics"
            element={<PerformanceDiagnostics />}
          />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockGetPerformance).toHaveBeenCalledWith("alex");
    });

    expect(screen.getByTestId("diagnostics-menu")).toHaveTextContent(
      "Menu for alex",
    );
  });
});
