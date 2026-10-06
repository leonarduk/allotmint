import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import ScenarioTester from "@/pages/ScenarioTester";
import type { ScenarioResult } from "@/types";

// Create mocks before vi.mock call
const mockGetEvents = vi.fn();
const mockGetOwners = vi.fn();
const mockGetPortfolio = vi.fn();
const mockRunScenario = vi.fn();
const mockRunFxScenario = vi.fn();

vi.mock("@/api", () => ({
  getEvents: () => mockGetEvents(),
  getOwners: () => mockGetOwners(),
  getPortfolio: (...args: unknown[]) => mockGetPortfolio(...args),
  runScenario: (params: any) => mockRunScenario(params),
  runFxScenario: (params: any) => mockRunFxScenario(params),
}));

const renderPage = () =>
  render(
    <MemoryRouter>
      <ScenarioTester />
    </MemoryRouter>,
  );

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
    mockRunFxScenario.mockReset();
    
    // Provide default mock implementations
    mockGetOwners.mockResolvedValue([]);
    mockGetPortfolio.mockResolvedValue({ holdings: [], cash: [] } as any);
  });

  it("links to the strategy stress test for the chosen event and horizons", async () => {
    mockGetEvents.mockResolvedValueOnce([{ id: "e1", name: "Event 1" }]);
    renderPage();
    expect(
      screen.queryByRole("link", { name: /Compare strategies/ }),
    ).toBeNull();
    await screen.findByRole("option", { name: "Event 1" });
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "e1" },
    });
    const link = await screen.findByRole("link", {
      name: /Compare strategies for this event/,
    });
    expect(link.getAttribute("href")).toBe("/strategy?stress_event=e1");
    fireEvent.click(screen.getByLabelText("1w"));
    fireEvent.click(screen.getByLabelText("1y"));
    expect(link.getAttribute("href")).toBe(
      "/strategy?stress_event=e1&horizons=1w%2C1y",
    );
  });

  it("fetches events and populates dropdown", async () => {
    mockGetEvents.mockResolvedValueOnce([{ id: "e1", name: "Event 1" }]);
    renderPage();
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

    renderPage();

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

  it("flags partially priced horizons and shows unavailable ones as a dash", async () => {
    mockGetEvents.mockResolvedValueOnce([{ id: "e1", name: "Event 1" }]);
    mockRunScenario.mockResolvedValueOnce([
      {
        owner: "Test Owner",
        horizons: {
          "1m": {
            baseline_total_value_gbp: 100,
            shocked_total_value_gbp: 80,
            coverage_pct: 62.4,
          },
          "1y": {
            baseline_total_value_gbp: 100,
            shocked_total_value_gbp: null,
            coverage_pct: 30,
          },
        },
      } as ScenarioResult,
    ]);

    renderPage();
    await screen.findByRole("option", { name: "Event 1" });
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "e1" },
    });
    fireEvent.click(screen.getByLabelText("1m"));
    fireEvent.click(screen.getByLabelText("1y"));
    fireEvent.click(screen.getByText("Run stress test"));

    await screen.findByText("Test Owner");
    expect(screen.getByText("-20.00%")).toBeInTheDocument();
    expect(screen.getByText("62% priced")).toBeInTheDocument();
    expect(screen.getByText("30% priced")).toBeInTheDocument();
    expect(screen.queryByText(new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(0))).toBeNull();
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
    renderPage();

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

    renderPage();

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

    renderPage();

    await screen.findByText("Alex Leonard");
    const [ownerCheckbox] = screen.getAllByRole("checkbox");
    fireEvent.click(ownerCheckbox);

    await screen.findByText("Loaded");

    expect(mockGetPortfolio).toHaveBeenCalledTimes(1);
  });

  it("requests the bare owner, not the owner::date dedupe key (#8576)", async () => {
    mockGetEvents.mockResolvedValueOnce([]);
    mockGetOwners.mockResolvedValueOnce([
      { owner: "alex", accounts: ["isa"], full_name: "Alex Leonard" },
      { owner: "beth", accounts: ["isa"], full_name: "Beth Leonard" },
    ]);
    mockGetPortfolio.mockResolvedValue({ accounts: [] } as any);

    renderPage();

    await screen.findByText("Beth Leonard");
    fireEvent.click(
      screen.getByRole("button", { name: /select all portfolios/i }),
    );

    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledTimes(2));
    const owners = mockGetPortfolio.mock.calls.map(([owner]) => owner);
    expect(owners.sort()).toEqual(["alex", "beth"]);
    for (const owner of owners) {
      expect(owner).not.toContain("::");
    }
  });

  it("does not refetch a loaded portfolio when a second owner is selected (#7105)", async () => {
    mockGetEvents.mockResolvedValueOnce([]);
    mockGetOwners.mockResolvedValueOnce([
      { owner: "alex", accounts: ["isa"], full_name: "Alex Leonard" },
      { owner: "beth", accounts: ["isa"], full_name: "Beth Leonard" },
    ]);
    mockGetPortfolio.mockResolvedValue({ accounts: [] } as any);

    renderPage();

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

    renderPage();

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

  it("retries a failed portfolio load when the same owner is re-selected (#7136)", async () => {
    mockGetEvents.mockResolvedValueOnce([]);
    mockGetOwners.mockResolvedValueOnce([
      { owner: "alex", accounts: ["isa"], full_name: "Alex Leonard" },
    ]);

    // First attempt fails.
    mockGetPortfolio.mockRejectedValueOnce(new Error("network down"));

    renderPage();

    await screen.findByText("Alex Leonard");
    const [ownerCheckbox] = screen.getAllByRole("checkbox");

    // Select the owner -> triggers fetch #1, which rejects.
    fireEvent.click(ownerCheckbox);
    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledTimes(1));

    // Let the rejection propagate through the .catch handler so the key is
    // removed from requestedPortfolioKeys before we retry.
    await new Promise((resolve) => setTimeout(resolve, 20));

    // Arm the retry to succeed.
    mockGetPortfolio.mockResolvedValueOnce({ accounts: [] } as any);

    // The checkbox is a toggle: the first click selected the owner, so we
    // must deselect and re-select to trigger a fresh load attempt.
    fireEvent.click(ownerCheckbox); // deselect
    fireEvent.click(ownerCheckbox); // re-select -> fetch #2

    // If the .catch handler failed to delete the key, the dedup guard would
    // suppress this call and the assertion below would fail.
    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledTimes(2));

    // And no further requests should fire once the retry succeeds.
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(mockGetPortfolio).toHaveBeenCalledTimes(2);
  });

  describe("currency shock", () => {
    const gbp = (v: number) =>
      new Intl.NumberFormat("en", { style: "currency", currency: "GBP" }).format(v);

    beforeEach(() => {
      mockGetEvents.mockResolvedValue([]);
    });

    it("runs a USD shock and shows GBP results, exposure and unconverted holdings", async () => {
      mockRunFxScenario.mockResolvedValueOnce([
        {
          owner: "alex",
          baseline_total_value_gbp: 1000,
          shocked_total_value_gbp: 960,
          delta_gbp: -40,
          exposed_value_gbp: 400,
          skipped_unknown_currency: 2,
          unconverted_holdings: [
            { ticker: "NOFX.N", currency: "USD", reason: "no stored FX rate" },
          ],
        },
      ]);
      renderPage();

      fireEvent.click(screen.getByRole("button", { name: "Run currency shock" }));

      await waitFor(() =>
        expect(mockRunFxScenario).toHaveBeenCalledWith({ currency: "USD", pct: -10 }),
      );
      expect(await screen.findByText(gbp(400))).toBeInTheDocument();
      expect(screen.getByText("USD exposure")).toBeInTheDocument();
      expect(screen.getByText(gbp(1000))).toBeInTheDocument();
      expect(screen.getByText(gbp(960))).toBeInTheDocument();
      expect(screen.getByText(gbp(-40))).toBeInTheDocument();
      expect(screen.getByText("-4.00%")).toBeInTheDocument();
      expect(screen.getByText(/NOFX\.N \(USD\)/)).toBeInTheDocument();
      expect(
        screen.getByText("2 holdings with an unknown currency were not shocked."),
      ).toBeInTheDocument();
    });

    it("states the sign convention for the chosen currency", () => {
      renderPage();

      fireEvent.click(screen.getByRole("button", { name: "EUR" }));

      expect(screen.getByText("Change in the GBP value of 1 EUR (%)")).toBeInTheDocument();
      expect(
        screen.getByText(/A negative change means EUR weakens against GBP/),
      ).toBeInTheDocument();
    });

    it.each([
      ["GBP", "-10", "GBP and GBX cannot move against GBP."],
      ["US", "-10", "Enter a 3-letter currency code."],
      ["USD", "-100", "Enter a change above -100% and at most 1000%."],
      ["USD", "1001", "Enter a change above -100% and at most 1000%."],
    ])("blocks currency %s with change %s", (currency, pct, message) => {
      renderPage();

      fireEvent.change(screen.getByLabelText("Currency"), { target: { value: currency } });
      fireEvent.change(screen.getByLabelText(/Change in the GBP value of 1/), {
        target: { value: pct },
      });

      expect(screen.getByRole("button", { name: "Run currency shock" })).toBeDisabled();
      expect(screen.getByText(message)).toBeInTheDocument();
      expect(mockRunFxScenario).not.toHaveBeenCalled();
    });

    it("shows the API error and no results when the shock fails", async () => {
      mockRunFxScenario.mockRejectedValueOnce(new Error("HTTP 400"));
      renderPage();

      fireEvent.click(screen.getByRole("button", { name: "Run currency shock" }));

      expect(await screen.findByText("HTTP 400")).toBeInTheDocument();
      expect(screen.queryByText("USD exposure")).not.toBeInTheDocument();
    });
  });
});
