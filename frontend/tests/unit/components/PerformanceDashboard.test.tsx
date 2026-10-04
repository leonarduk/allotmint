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

  it("names the benchmark used for alpha and tracking error (#7230)", async () => {
    render(
      <MemoryRouter>
        <PerformanceDashboard owner="jane" />
      </MemoryRouter>,
    );

    expect(await screen.findAllByText("vs VWRL.L")).toHaveLength(2);
    expect(
      screen.getByRole("button", { name: "What does Alpha vs Benchmark mean?" }),
    ).toBeInTheDocument();
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

  // #8570: every metric is a fraction from the API. It is formatted directly
  // (no "|x| > 1 means percent" guessing) and implausible values show N/A.
  describe("metric units and plausibility (#8570)", () => {
    type Metrics = {
      alpha: number;
      trackingError: number;
      maxDrawdown: number;
      twr: number;
      xirr: number;
    };

    const renderWith = async (m: Metrics) => {
      vi.mocked(getAlphaVsBenchmark).mockResolvedValueOnce({
        alpha_vs_benchmark: m.alpha,
      });
      vi.mocked(getTrackingError).mockResolvedValueOnce({
        tracking_error: m.trackingError,
      });
      vi.mocked(getMaxDrawdown).mockResolvedValueOnce({
        max_drawdown: m.maxDrawdown,
        peak: null,
        trough: null,
        series: [],
      });
      vi.mocked(getPerformance).mockResolvedValueOnce({
        history: [{ date: "2024-03-01", value: 1000 }],
        time_weighted_return: m.twr,
        xirr: m.xirr,
        reportingDate: "2024-03-31",
        previousDate: "2024-02-29",
      });
      render(
        <MemoryRouter>
          <PerformanceDashboard owner="jane" />
        </MemoryRouter>,
      );
      await screen.findByTestId("reporting-date-summary");
    };

    const testIds = {
      alpha: "metric-alpha",
      trackingError: "metric-tracking-error",
      maxDrawdown: "metric-max-drawdown",
      twr: "metric-twr",
      xirr: "metric-xirr",
    } as const;

    it("formats normal fractions as percentages", async () => {
      await renderWith({
        alpha: 0.0123,
        trackingError: 0.045,
        maxDrawdown: -0.35,
        twr: 0.0596,
        xirr: 0.071,
      });
      expect(screen.getByTestId(testIds.alpha)).toHaveTextContent("1.23%");
      expect(screen.getByTestId(testIds.trackingError)).toHaveTextContent("4.50%");
      expect(screen.getByTestId(testIds.maxDrawdown)).toHaveTextContent("-35.00%");
      expect(screen.getByTestId(testIds.twr)).toHaveTextContent("5.96%");
      expect(screen.getByTestId(testIds.xirr)).toHaveTextContent("7.10%");
    });

    it("renders genuine values above 100% (1.5 -> 150.00%) instead of dividing by 100", async () => {
      await renderWith({
        alpha: 1.5,
        trackingError: 1.5,
        // Drawdown is bounded at -100%, so the full-loss edge is the
        // largest genuine magnitude it can take.
        maxDrawdown: -1,
        twr: 1.5,
        xirr: 1.5,
      });
      expect(screen.getByTestId(testIds.alpha)).toHaveTextContent("150.00%");
      expect(screen.getByTestId(testIds.trackingError)).toHaveTextContent("150.00%");
      expect(screen.getByTestId(testIds.maxDrawdown)).toHaveTextContent("-100.00%");
      expect(screen.getByTestId(testIds.twr)).toHaveTextContent("150.00%");
      expect(screen.getByTestId(testIds.xirr)).toHaveTextContent("150.00%");
    });

    it("renders implausible values (e.g. XIRR 14159.17) as N/A with an unreliable tooltip", async () => {
      await renderWith({
        alpha: 14159.17,
        trackingError: 2.5,
        maxDrawdown: -1.5,
        twr: -14159.17,
        xirr: 14159.17,
      });
      for (const id of Object.values(testIds)) {
        const el = screen.getByTestId(id);
        expect(el).toHaveTextContent(/^N\/A$/);
        expect(el).toHaveAttribute("data-unreliable", "true");
        expect(el).toHaveAttribute(
          "title",
          expect.stringMatching(/looks unreliable/),
        );
      }
      expect(screen.queryByText("141.59%")).not.toBeInTheDocument();
    });

    it("renders missing values as plain N/A without the unreliable tooltip", async () => {
      vi.mocked(getPerformance).mockResolvedValueOnce({
        history: [{ date: "2024-03-01", value: 1000 }],
        time_weighted_return: null,
        xirr: null,
        reportingDate: "2024-03-31",
        previousDate: "2024-02-29",
      });
      render(
        <MemoryRouter>
          <PerformanceDashboard owner="jane" />
        </MemoryRouter>,
      );
      await screen.findByTestId("reporting-date-summary");
      const xirrEl = screen.getByTestId(testIds.xirr);
      expect(xirrEl).toHaveTextContent("N/A");
      expect(xirrEl).not.toHaveAttribute("data-unreliable");
    });
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

    it("computes group alpha and tracking error against the benchmark when both endpoints succeed", async () => {
      render(
        <MemoryRouter>
          <PerformanceDashboard owner={null} group="all" />
        </MemoryRouter>,
      );

      await screen.findByTestId("reporting-date-summary");
      expect(screen.getByText("Alpha vs Benchmark")).toBeInTheDocument();
      expect(screen.getByText("3.00%")).toBeInTheDocument();
      expect(screen.getByText("Tracking Error")).toBeInTheDocument();
      expect(screen.getByText("4.00%")).toBeInTheDocument();
      expect(
        screen.queryByTestId("performance-metrics-unavailable-warning"),
      ).not.toBeInTheDocument();
    });

    // DeepSeek review round 2 (#7228): a single failing group metric
    // endpoint used to blank the entire dashboard via Promise.all. These
    // cases confirm each metric degrades to "unavailable" independently
    // instead, and that the rest of the page still renders.
    it("renders group alpha as unavailable, without blanking the dashboard, when its endpoint fails", async () => {
      vi.mocked(getGroupAlphaVsBenchmark).mockRejectedValueOnce(
        new Error("HTTP 404 - Not Found"),
      );

      render(
        <MemoryRouter>
          <PerformanceDashboard owner={null} group="all" />
        </MemoryRouter>,
      );

      expect(
        await screen.findByTestId("performance-metrics-unavailable-warning"),
      ).toHaveTextContent("Alpha vs Benchmark");
      // The chart data and other metrics still loaded successfully.
      expect(
        await screen.findByTestId("reporting-date-summary"),
      ).toHaveTextContent("Reporting date: 2024-03-31");
      expect(screen.getByText("Tracking Error")).toBeInTheDocument();
      expect(screen.getByText("4.00%")).toBeInTheDocument();
    });

    it("renders group tracking error as unavailable, without blanking the dashboard, when its endpoint fails", async () => {
      vi.mocked(getGroupTrackingError).mockRejectedValueOnce(
        new Error("HTTP 500 - Internal Server Error"),
      );

      render(
        <MemoryRouter>
          <PerformanceDashboard owner={null} group="all" />
        </MemoryRouter>,
      );

      expect(
        await screen.findByTestId("performance-metrics-unavailable-warning"),
      ).toHaveTextContent("Tracking Error");
      expect(
        await screen.findByTestId("reporting-date-summary"),
      ).toHaveTextContent("Reporting date: 2024-03-31");
      expect(screen.getByText("Alpha vs Benchmark")).toBeInTheDocument();
      expect(screen.getByText("3.00%")).toBeInTheDocument();
    });

    it("shows a chart-unavailable message, without losing alpha/tracking-error, when getGroupPerformance fails entirely", async () => {
      vi.mocked(getGroupPerformance).mockRejectedValueOnce(
        new Error("HTTP 503 - Service Unavailable"),
      );

      render(
        <MemoryRouter>
          <PerformanceDashboard owner={null} group="all" />
        </MemoryRouter>,
      );

      expect(
        await screen.findByTestId("performance-chart-unavailable"),
      ).toBeInTheDocument();
    });
  });
});
