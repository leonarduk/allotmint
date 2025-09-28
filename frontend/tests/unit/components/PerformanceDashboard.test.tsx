import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import i18n from "@/i18n";
import { PerformanceDashboard } from "@/components/PerformanceDashboard";
import {
  getPerformance,
  getAlphaVsBenchmark,
  getTrackingError,
  getMaxDrawdown,
} from "@/api";

vi.mock("@/api", () => ({
  getPerformance: vi.fn(),
  getAlphaVsBenchmark: vi.fn(),
  getTrackingError: vi.fn(),
  getMaxDrawdown: vi.fn(),
}));

describe("PerformanceDashboard", () => {
  beforeEach(() => {
    i18n.changeLanguage("en");
    vi.mocked(getAlphaVsBenchmark).mockResolvedValue({
      alpha_vs_benchmark: 0.01,
    });
    vi.mocked(getTrackingError).mockResolvedValue({
      tracking_error: 0.02,
    });
    vi.mocked(getMaxDrawdown).mockResolvedValue({
      max_drawdown: 0.03,
    });
    vi.mocked(getPerformance).mockResolvedValue({
      history: [{ date: "2024-03-01", value: 1000 }],
      time_weighted_return: 0.04,
      xirr: 0.05,
      reportingDate: "2024-03-31",
      previousDate: "2024-02-29",
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders reporting and previous date summary", async () => {
    render(
      <MemoryRouter>
        <PerformanceDashboard owner="jane" />
      </MemoryRouter>,
    );

    expect(
      await screen.findByTestId("reporting-date-summary"),
    ).toHaveTextContent("Reporting date: 2024-03-31");
    expect(screen.getByTestId("previous-date-summary")).toHaveTextContent(
      "Previous date: 2024-02-29",
    );
  });
});
