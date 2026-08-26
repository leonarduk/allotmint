import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import ScenarioTester from "@/pages/ScenarioTester";
import type { ScenarioResult } from "@/types";

// Create mocks before vi.mock call
const mockGetEvents = vi.fn();
const mockGetOwners = vi.fn();
const mockGetPortfolio = vi.fn();
const mockRunScenario = vi.fn();

vi.mock("@/api", () => ({
  getEvents: () => mockGetEvents(),
  getOwners: () => mockGetOwners(),
  getPortfolio: (...args: unknown[]) => mockGetPortfolio(...args),
  runScenario: (params: any) => mockRunScenario(params),
}));

describe("ScenarioTester page", () => {
  beforeEach(() => {
    // The page persists scenario.selectedOwners to localStorage, so without
    // this a previous test's selection is restored on mount and fires extra
    // getPortfolio calls in the next one.
    localStorage.clear();
    mockGetEvents.mockReset();
    mockGetOwners.mockReset();
    mockGetPortfolio.mockReset();
    mockRunScenario.mockReset();
    
    // Provide default mock implementations
    mockGetOwners.mockResolvedValue([]);
    mockGetPortfolio.mockResolvedValue({ holdings: [], cash: [] } as any);
  });

  it("fetches events and populates dropdown", async () => {
    mockGetEvents.mockResolvedValueOnce([{ id: "e1", name: "Event 1" }]);
    render(<ScenarioTester />);
    await waitFor(() => expect(mockGetEvents).toHaveBeenCalled());
    expect(
      await screen.findByRole("option", { name: "Event 1" }),
    ).toBeInTheDocument();
  });

  it("runs scenario and displays results in table", async () => {
    mockGetEvents.mockResolvedValueOnce([{ id: "e1", name: "Event 1" }]);
    mockRunScenario.mockResolvedValueOnce([
      {
        owner: "Test Owner",
        horizons: {
          "1d": {
            baseline_total_value_gbp: 100,
            shocked_total_value_gbp: 110,
          },
          "1w": {
            baseline_total_value_gbp: 200,
            shocked_total_value_gbp: 180,
          },
        },
      } as ScenarioResult,
    ]);

    render(<ScenarioTester />);

    await screen.findByRole("option", { name: "Event 1" });

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "e1" },
    });
    fireEvent.click(screen.getByLabelText("1d"));
    fireEvent.click(screen.getByLabelText("1w"));

    const runButton = screen.getByText("Run stress test");
    expect(runButton).not.toBeDisabled();

    fireEvent.click(runButton);

    await waitFor(() =>
      expect(mockRunScenario).toHaveBeenCalledWith({
        event_id: "e1",
        horizons: ["1d", "1w"],
      }),
    );

    const fmt = new Intl.NumberFormat("en-GB", {
      style: "currency",
      currency: "GBP",
    });

    // findByText waits for React to re-render after the async runScenario
    // response arrives; getByText would race the render and fail intermittently.
    await screen.findByText("Test Owner");
    expect(screen.getByText(fmt.format(100))).toBeInTheDocument();
    expect(screen.getByText(fmt.format(110))).toBeInTheDocument();
    expect(screen.getByText("10.00%")).toBeInTheDocument();
    expect(screen.getByText(fmt.format(200))).toBeInTheDocument();
    expect(screen.getByText(fmt.format(180))).toBeInTheDocument();
    expect(screen.getByText("-10.00%")).toBeInTheDocument();
  });

  it("disables Apply button until valid inputs provided", async () => {
    mockGetEvents.mockResolvedValueOnce([{ id: "e1", name: "Event 1" }]);
    mockRunScenario.mockResolvedValueOnce([
      {
        owner: "Test Owner",
        horizons: {
          "1d": {
            baseline_total_value_gbp: 100,
            shocked_total_value_gbp: 110,
          },
        },
        baseline_total_value_gbp: 100,
        shocked_total_value_gbp: 110,
        delta_gbp: 10,
      } as ScenarioResult,
    ]);
    render(<ScenarioTester />);

    await screen.findByRole("combobox");
    const runButton = screen.getByText("Run stress test");

    expect(runButton).toBeDisabled();
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "e1" },
    });
    expect(runButton).toBeDisabled();
    fireEvent.click(screen.getByLabelText("1d"));
    expect(runButton).not.toBeDisabled();
    fireEvent.click(runButton);
    await waitFor(() => expect(mockRunScenario).toHaveBeenCalled());
    expect(screen.getByText("Test Owner")).toBeInTheDocument();
  });

  it("shows error message on failure", async () => {
    mockGetEvents.mockResolvedValueOnce([{ id: "e1", name: "Event 1" }]);
    mockRunScenario.mockRejectedValueOnce(new Error("fail"));

    render(<ScenarioTester />);

    await screen.findByRole("combobox");
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "e1" } });
    fireEvent.click(screen.getByLabelText("1d"));

    fireEvent.click(screen.getByText("Run stress test"));

    expect(await screen.findByText("fail")).toBeInTheDocument();
  });

  it("fires exactly one GET /portfolio/{owner} request when a single portfolio is selected (#7105)", async () => {
    mockGetEvents.mockResolvedValueOnce([]);
    mockGetOwners.mockResolvedValueOnce([
      { owner: "alex", accounts: ["isa"], full_name: "Alex Leonard" },
    ]);
    mockGetPortfolio.mockResolvedValue({
      accounts: [],
    } as any);

    render(<ScenarioTester />);

    await screen.findByText("Alex Leonard");
    const [ownerCheckbox] = screen.getAllByRole("checkbox");
    fireEvent.click(ownerCheckbox);

    await screen.findByText("Loaded");

    expect(mockGetPortfolio).toHaveBeenCalledTimes(1);
  });

  it("does not refetch a loaded portfolio when a second owner is selected (#7105)", async () => {
    mockGetEvents.mockResolvedValueOnce([]);
    mockGetOwners.mockResolvedValueOnce([
      { owner: "alex", accounts: ["isa"], full_name: "Alex Leonard" },
      { owner: "beth", accounts: ["isa"], full_name: "Beth Leonard" },
    ]);
    mockGetPortfolio.mockResolvedValue({ accounts: [] } as any);

    render(<ScenarioTester />);

    await screen.findByText("Alex Leonard");
    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]);
    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledTimes(1));

    // Selecting a second owner re-runs the load effect for BOTH owners. Alex
    // is already loaded, so only Beth should hit the network.
    fireEvent.click(checkboxes[1]);
    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledTimes(2));

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(mockGetPortfolio).toHaveBeenCalledTimes(2);
  });

  it("does not refetch a loaded portfolio behind a newly-queued one on Select all (#7105)", async () => {
    mockGetEvents.mockResolvedValueOnce([]);
    mockGetOwners.mockResolvedValueOnce([
      { owner: "alex", accounts: ["isa"], full_name: "Alex Leonard" },
      { owner: "beth", accounts: ["isa"], full_name: "Beth Leonard" },
    ]);
    mockGetPortfolio.mockResolvedValue({ accounts: [] } as any);

    render(<ScenarioTester />);

    await screen.findByText("Beth Leonard");
    // Load the SECOND owner first, so "Select all" walks an unloaded owner
    // (alex) before the loaded one (beth).
    fireEvent.click(screen.getAllByRole("checkbox")[1]);
    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole("button", { name: /select all portfolios/i }),
    );

    // Only alex is missing, so exactly one further request may go out. Beth's
    // guard must not be skipped just because alex queued an update first.
    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledTimes(2));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(mockGetPortfolio).toHaveBeenCalledTimes(2);
  });
});
