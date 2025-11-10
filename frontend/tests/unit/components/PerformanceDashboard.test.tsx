import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
      max_drawdown: -0.35,
      peak: { date: "2024-02-01", value: 2100 },
      trough: { date: "2024-03-10", value: 1300, drawdown: -0.38 },
      series: [
        {
          date: "2024-02-01",
          portfolio_value: 2100,
          running_max: 2100,
          drawdown: 0,
        },
        {
          date: "2024-02-15",
          portfolio_value: 2000,
          running_max: 2100,
          drawdown: -0.0476,
        },
        {
          date: "2024-03-10",
          portfolio_value: 1300,
          running_max: 2100,
          drawdown: -0.381,
        },
      ],
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

  it("allows drilling into drawdown details on demand", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <PerformanceDashboard owner="jane" />
      </MemoryRouter>,
    );

    const toggle = await screen.findByRole("button", {
      name: /Explain this drop/i,
    });
    await user.click(toggle);

    expect(
      await screen.findByText(/Largest drop runs from/),
    ).toBeInTheDocument();
    const diagLinks = screen.getAllByRole("link", {
      name: /Open diagnostics/i,
    });
    expect(diagLinks[0]).toBeInTheDocument();
  });

  it("auto-expands suspicious drawdowns", async () => {
    vi.mocked(getMaxDrawdown).mockResolvedValueOnce({
      max_drawdown: -0.95,
      peak: { date: "2024-02-01", value: 2100 },
      trough: { date: "2024-03-10", value: 100, drawdown: -0.952 },
      series: [
        {
          date: "2024-02-01",
          portfolio_value: 2100,
          running_max: 2100,
          drawdown: 0,
        },
        {
          date: "2024-03-10",
          portfolio_value: 100,
          running_max: 2100,
          drawdown: -0.952,
        },
      ],
    });

    render(
      <MemoryRouter>
        <PerformanceDashboard owner="jane" />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/Drops larger than 90%/i),
    ).toBeInTheDocument();
  });
});
