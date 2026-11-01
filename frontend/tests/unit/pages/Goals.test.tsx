import type { ReactNode } from "react";
import { render, screen, waitFor, act, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, beforeEach, vi } from "vitest";
import i18n from "@/i18n";
import { configContext, type ConfigContextValue } from "@/ConfigContext";
import { clearReportingRateCache } from "@/hooks/useReportingCurrency";
import Goals from "@/pages/Goals";
import { formatGoalDate, parseGoalForm } from "@/lib/goalForm";
import { parseCurrentAmount, progressPercent, type GoalProjection } from "@/lib/goalProgress";

const mockGetGoals = vi.hoisted(() => vi.fn());
const mockCreateGoal = vi.hoisted(() => vi.fn());
const mockGetGoal = vi.hoisted(() => vi.fn());
const mockGetGbpRate = vi.hoisted(() => vi.fn());
const mockRecordGoalProgress = vi.hoisted(() => vi.fn());

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    getGoals: mockGetGoals,
    createGoal: mockCreateGoal,
    getGoal: mockGetGoal,
    getGbpRate: mockGetGbpRate,
    recordGoalProgress: mockRecordGoalProgress,
  };
});

function withCurrency(reportingCurrency: string) {
  const value = { reportingCurrency } as unknown as ConfigContextValue;
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <MemoryRouter>
        <configContext.Provider value={value}>{children}</configContext.Provider>
      </MemoryRouter>
    );
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  clearReportingRateCache();
  mockGetGoals.mockResolvedValue([]);
});

describe("Goals page", () => {
  it("renders translated strings", async () => {
    await act(async () => {
      await i18n.changeLanguage("fr");
    });
    const { unmount } = render(<Goals />, { wrapper: MemoryRouter });
    expect(
      await screen.findByRole("heading", { name: "Objectifs" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Ajouter un objectif" })
    ).toBeInTheDocument();
    await waitFor(() => expect(mockGetGoals).toHaveBeenCalledTimes(1));
    unmount();
    await act(async () => {
      await i18n.changeLanguage("en");
    });
  });

  it("labels every input", async () => {
    render(<Goals />, { wrapper: MemoryRouter });
    expect(screen.getByLabelText("Name")).toBeInTheDocument();
    expect(screen.getByLabelText("Target Amount")).toHaveValue(null);
    expect(screen.getByLabelText("Target Date")).toBeInTheDocument();
    expect(screen.getByLabelText("Current Amount:")).toHaveAccessibleDescription(
      /used to calculate progress/i
    );
    await waitFor(() => expect(mockGetGoals).toHaveBeenCalled());
  });

  it("shows a validation message on empty submit and keeps the form", async () => {
    render(<Goals />, { wrapper: MemoryRouter });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "House" } });
    fireEvent.click(screen.getByRole("button", { name: "Add Goal" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/enter a name/i);
    expect(screen.getByLabelText("Name")).toHaveValue("House");
    expect(mockCreateGoal).not.toHaveBeenCalled();
  });

  it("surfaces a save failure", async () => {
    mockCreateGoal.mockRejectedValue(new Error("boom"));
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(<Goals />, { wrapper: MemoryRouter });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "House" } });
    fireEvent.change(screen.getByLabelText("Target Amount"), { target: { value: "50000" } });
    fireEvent.change(screen.getByLabelText("Target Date"), { target: { value: "2030-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Add Goal" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not save/i);
    expect(mockCreateGoal).toHaveBeenCalledWith({
      name: "House",
      target_amount: 50000,
      target_date: "2030-01-01",
    });
  });

  it("renders saved goals with formatted currency, localised date and a separate View button", async () => {
    mockGetGoals.mockResolvedValue([
      { name: "House deposit", target_amount: 50000, target_date: "2030-01-01" },
    ]);
    render(<Goals />, { wrapper: withCurrency("GBP") });
    const line = await screen.findByText(/House deposit/);
    expect(line).toHaveTextContent("£50,000.00");
    expect(line).toHaveTextContent(formatGoalDate("2030-01-01", "en"));
    expect(line).not.toHaveTextContent("2030-01-01");
    expect(line).not.toHaveTextContent("View");
    expect(screen.getByRole("button", { name: "View" })).toBeInTheDocument();
  });

  it("shows goal amounts in the configured base currency, not hardcoded GBP", async () => {
    mockGetGbpRate.mockResolvedValue({ currency: "USD", gbp_per_unit: 0.8, source: "test" });
    mockGetGoals.mockResolvedValue([
      { name: "House deposit", target_amount: 50000, target_date: "2030-01-01" },
    ]);
    render(<Goals />, { wrapper: withCurrency("USD") });
    const line = await screen.findByText(/House deposit/);
    // 50,000 GBP at 0.8 GBP per USD.
    await waitFor(() => expect(line).toHaveTextContent("$62,500.00"));
    expect(line).not.toHaveTextContent("£");
    expect(mockGetGbpRate).toHaveBeenCalledWith("USD");
  });
});

const HOUSE = { name: "House deposit", target_amount: 50000, target_date: "2030-01-01" };

const projection = (overrides: Partial<GoalProjection>): GoalProjection => ({
  status: "insufficient_history",
  method: "linear_first_to_latest",
  points: 1,
  min_points: 2,
  min_days: 30,
  history_start: null,
  history_end: null,
  projected_date: null,
  on_track: null,
  monthly_rate: null,
  ...overrides,
});

describe("Goals page progress and projection", () => {
  beforeEach(() => {
    mockGetGoals.mockResolvedValue([HOUSE]);
  });

  it("views an entered amount read-only and shows a progress bar with formatted amounts", async () => {
    mockGetGoal.mockResolvedValue({
      ...HOUSE,
      progress: 0.248,
      current_amount: 12400,
      trades: [],
      projection: projection({}),
    });
    render(<Goals />, { wrapper: MemoryRouter });
    fireEvent.change(screen.getByLabelText("Current Amount:"), { target: { value: "12400" } });
    fireEvent.click(await screen.findByRole("button", { name: "View" }));

    const bar = await screen.findByRole("progressbar", { name: "Progress towards House deposit" });
    expect(bar).toHaveAttribute("value", "25");
    expect(screen.getByText("£12,400.00 of £50,000.00 (25%)")).toBeInTheDocument();
    // Viewing never writes history.
    expect(mockGetGoal).toHaveBeenCalledWith("House deposit", 12400);
    expect(mockRecordGoalProgress).not.toHaveBeenCalled();
    // One data point: no projection, and the page says why.
    expect(screen.getByText(/not enough history/i)).toHaveTextContent("at least 2 different dates");
    expect(screen.queryByText(/on track/i)).not.toBeInTheDocument();
  });

  it("does not show 0% when the current amount is unknown", async () => {
    mockGetGoal.mockResolvedValue({
      ...HOUSE,
      progress: null,
      current_amount: null,
      trades: null,
      projection: projection({ points: 0 }),
    });
    render(<Goals />, { wrapper: MemoryRouter });
    fireEvent.click(await screen.findByRole("button", { name: "View" }));

    expect(await screen.findByText(/enter your current amount/i)).toBeInTheDocument();
    expect(mockGetGoal).toHaveBeenCalledWith("House deposit", undefined);
    expect(mockRecordGoalProgress).not.toHaveBeenCalled();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.queryByText(/0%/)).not.toBeInTheDocument();
  });

  it("records progress only through the explicit Record progress button", async () => {
    mockRecordGoalProgress.mockResolvedValue({
      ...HOUSE,
      progress: 0.2,
      current_amount: 10000,
      trades: [],
      projection: projection({}),
    });
    render(<Goals />, { wrapper: MemoryRouter });
    const recordButton = await screen.findByRole("button", { name: "Record progress" });
    // Nothing to record until an amount is entered.
    expect(recordButton).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Current Amount:"), { target: { value: "10000" } });
    expect(recordButton).toBeEnabled();
    fireEvent.click(recordButton);

    expect(await screen.findByText("£10,000.00 of £50,000.00 (20%)")).toBeInTheDocument();
    expect(mockRecordGoalProgress).toHaveBeenCalledTimes(1);
    expect(mockRecordGoalProgress).toHaveBeenCalledWith("House deposit", 10000);
    expect(mockGetGoal).not.toHaveBeenCalled();
  });

  it("surfaces a failure to record progress", async () => {
    mockRecordGoalProgress.mockRejectedValue(new Error("boom"));
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(<Goals />, { wrapper: MemoryRouter });
    fireEvent.change(screen.getByLabelText("Current Amount:"), { target: { value: "100" } });
    fireEvent.click(await screen.findByRole("button", { name: "Record progress" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not record progress/i);
  });

  it("explains when recorded amounts are not increasing", async () => {
    mockGetGoal.mockResolvedValue({
      ...HOUSE,
      progress: 0.1,
      current_amount: 5000,
      trades: [],
      projection: projection({ status: "not_progressing", points: 2, monthly_rate: -50 }),
    });
    render(<Goals />, { wrapper: MemoryRouter });
    fireEvent.click(await screen.findByRole("button", { name: "View" }));

    expect(await screen.findByText(/not increasing/i)).toBeInTheDocument();
    expect(screen.queryByText(/on track/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/assumes you keep saving/i)).not.toBeInTheDocument();
  });

  it("says when the target has been reached", async () => {
    mockGetGoal.mockResolvedValue({
      ...HOUSE,
      progress: 1,
      current_amount: 52000,
      trades: [],
      projection: projection({ status: "reached", points: 1, on_track: true }),
    });
    render(<Goals />, { wrapper: MemoryRouter });
    fireEvent.click(await screen.findByRole("button", { name: "View" }));

    expect(await screen.findByText("Target reached.")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("value", "100");
    expect(screen.queryByText(/not enough history/i)).not.toBeInTheDocument();
  });

  it("shows a projected date with its assumptions when there is enough history", async () => {
    mockGetGoal.mockResolvedValue({
      ...HOUSE,
      progress: 0.25,
      current_amount: 12500,
      trades: [],
      projection: projection({
        status: "projected",
        points: 3,
        history_start: "2026-01-01",
        history_end: "2026-06-01",
        projected_date: "2029-12-01",
        on_track: true,
        monthly_rate: 800,
      }),
    });
    render(<Goals />, { wrapper: MemoryRouter });
    fireEvent.click(await screen.findByRole("button", { name: "View" }));

    expect(await screen.findByText(/on track for/i)).toHaveTextContent(formatGoalDate("2029-12-01", "en"));
    const assumptions = screen.getByText(/assumes you keep saving/i);
    expect(assumptions).toHaveTextContent("£800.00 a month");
    expect(assumptions).toHaveTextContent("from 3 recorded amounts");
  });

  it("says when the projection lands after the target date", async () => {
    mockGetGoal.mockResolvedValue({
      ...HOUSE,
      progress: 0.1,
      current_amount: 5000,
      trades: [],
      projection: projection({
        status: "projected",
        points: 2,
        history_start: "2026-01-01",
        history_end: "2026-03-01",
        projected_date: "2035-01-01",
        on_track: false,
        monthly_rate: 100,
      }),
    });
    render(<Goals />, { wrapper: MemoryRouter });
    fireEvent.click(await screen.findByRole("button", { name: "View" }));

    expect(await screen.findByText(/after your target date/i)).toHaveTextContent(
      formatGoalDate("2030-01-01", "en"),
    );
  });
});

describe("parseCurrentAmount", () => {
  it("treats empty or invalid input as unknown rather than zero", () => {
    expect(parseCurrentAmount("")).toBeNull();
    expect(parseCurrentAmount("   ")).toBeNull();
    expect(parseCurrentAmount("abc")).toBeNull();
    expect(parseCurrentAmount("-5")).toBeNull();
    expect(parseCurrentAmount("0")).toBe(0);
    expect(parseCurrentAmount("12400.5")).toBe(12400.5);
  });
});

describe("progressPercent", () => {
  it("rounds and clamps to 0..100", () => {
    expect(progressPercent(0.248)).toBe(25);
    expect(progressPercent(1.4)).toBe(100);
    expect(progressPercent(-0.2)).toBe(0);
    expect(progressPercent(Number.NaN)).toBe(0);
  });
});

describe("parseGoalForm", () => {
  it("rejects missing or non-positive values", () => {
    const base = { name: "A", target_amount: "10", target_date: "2030-01-01" };
    expect(parseGoalForm(base)).toEqual({ name: "A", target_amount: 10, target_date: "2030-01-01" });
    expect(parseGoalForm({ ...base, name: "  " })).toBeNull();
    expect(parseGoalForm({ ...base, target_amount: "" })).toBeNull();
    expect(parseGoalForm({ ...base, target_amount: "0" })).toBeNull();
    expect(parseGoalForm({ ...base, target_date: "" })).toBeNull();
  });
});

describe("formatGoalDate", () => {
  it("formats ISO dates without a UTC day shift and passes through junk", () => {
    expect(formatGoalDate("2030-01-01", "en-GB")).toBe("1 Jan 2030");
    expect(formatGoalDate("not-a-date", "en-GB")).toBe("not-a-date");
  });
});
