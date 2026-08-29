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
  getGroupPerformance,
  getGroupAlphaVsBenchmark,
  getGroupTrackingError,
  getGroupMaxDrawdown,
} from "@/api";

vi.mock("@/api", () => ({
  getPerformance: vi.fn(),
  getAlphaVsBenchmark: vi.fn(),
  getTrackingError: vi.fn(),
  getMaxDrawdown: vi.fn(),
  getGroupPerformance: vi.fn(),
  getGroupAlphaVsBenchmark: vi.fn(),
  getGroupTrackingError: vi.fn(),
  getGroupMaxDrawdown: vi.fn(),
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

  describe("group scope (#7228)", () => {
    beforeEach(() => {
      vi.mocked(getGroupAlphaVsBenchmark).mockResolvedValue({
        alpha_vs_benchmark: 0.03,
      });
      vi.mocked(getGroupTrackingError).mockResolvedValue({
        tracking_error: 0.04,
      });
      vi.mocked(getGroupMaxDrawdown).mockResolvedValue({
        max_drawdown: -0.2,
        peak: null,
        trough: null,
        series: [],
      });
      vi.mocked(getGroupPerformance).mockResolvedValue({
        history: [{ date: "2024-03-01", value: 5000 }],
        time_weighted_return: 0.06,
        xirr: 0.07,
        reportingDate: "2024-03-31",
        previousDate: "2024-02-29",
      });
    });

    it("fetches the combined group series instead of an owner's when group is set", async () => {
      render(
        <MemoryRouter>
          <PerformanceDashboard owner={null} group="all" />
        </MemoryRouter>,
      );

      expect(
        await screen.findByTestId("reporting-date-summary"),
      ).toHaveTextContent("Reporting date: 2024-03-31");

      expect(getGroupPerformance).toHaveBeenCalledWith("all", 365, false, undefined);
      expect(getGroupAlphaVsBenchmark).toHaveBeenCalledWith("all", "VWRL.L", 365);
      expect(getGroupTrackingError).toHaveBeenCalledWith("all", "VWRL.L", 365);
      expect(getGroupMaxDrawdown).toHaveBeenCalledWith("all", 365);
      expect(getPerformance).not.toHaveBeenCalled();
      expect(getAlphaVsBenchmark).not.toHaveBeenCalled();
    });

    it("hides the owner-only diagnostics link in group scope", async () => {
      render(
        <MemoryRouter>
          <PerformanceDashboard owner={null} group="all" />
        </MemoryRouter>,
      );

      await screen.findByTestId("reporting-date-summary");
      expect(
        screen.queryByRole("link", { name: /Open diagnostics/i }),
      ).not.toBeInTheDocument();
    });

    it("prefers group scope over a stale owner value", async () => {
      render(
        <MemoryRouter>
          <PerformanceDashboard owner="jane" group="all" />
        </MemoryRouter>,
      );

      await screen.findByTestId("reporting-date-summary");
      expect(getGroupPerformance).toHaveBeenCalledWith("all", 365, false, undefined);
      expect(getPerformance).not.toHaveBeenCalled();
    });

    it("warns when TWR/XIRR are partial because a member's ledger is missing (#7228)", async () => {
      vi.mocked(getGroupPerformance).mockResolvedValueOnce({
        history: [{ date: "2024-03-01", value: 5000 }],
        time_weighted_return: 0.06,
        xirr: 0.07,
        reportingDate: "2024-03-31",
        previousDate: "2024-02-29",
        partial: true,
        missingMembers: ["joe"],
      });

      render(
        <MemoryRouter>
          <PerformanceDashboard owner={null} group="all" />
        </MemoryRouter>,
      );

      expect(
        await screen.findByTestId("performance-partial-warning"),
      ).toHaveTextContent("joe");
    });

    it("shows no partial warning when group data is complete", async () => {
      render(
        <MemoryRouter>
          <PerformanceDashboard owner={null} group="all" />
        </MemoryRouter>,
      );

      await screen.findByTestId("reporting-date-summary");
      expect(
        screen.queryByTestId("performance-partial-warning"),
      ).not.toBeInTheDocument();
    });
  });
});
