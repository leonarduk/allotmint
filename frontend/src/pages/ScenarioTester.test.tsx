import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import ScenarioTester from "./ScenarioTester";
import * as api from "../api";
import type { ScenarioResult } from "../types";

vi.mock("../api");

const mockGetEvents = vi.mocked(api.getEvents);
const mockRunScenario = vi.mocked(api.runScenario);

describe("ScenarioTester page", () => {
  beforeEach(() => {
    mockGetEvents.mockReset();
    mockRunScenario.mockReset();
  });

  it("runs scenario and displays results in table", async () => {
    mockGetEvents.mockResolvedValueOnce([{ id: "e1", name: "Event 1" }]);
    mockRunScenario.mockResolvedValueOnce([
      {
        owner: "Test Owner",
        horizons: {
          "1d": { baseline: 100, shocked: 110 },
          "1w": { baseline: 200, shocked: 180 },
        },
        baseline_total_value_gbp: 100,
        shocked_total_value_gbp: 110,
        delta_gbp: 10,
      } as ScenarioResult,
    ]);

    render(<ScenarioTester />);

    await screen.findByRole("option", { name: "Event 1" });

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "e1" },
    });
    fireEvent.click(screen.getByLabelText("1d"));
    fireEvent.click(screen.getByLabelText("1w"));

    const apply = screen.getByText("Apply");
    expect(apply).not.toBeDisabled();

    fireEvent.click(apply);

    await waitFor(() =>
      expect(mockRunScenario).toHaveBeenCalledWith("e1", ["1d", "1w"]),
    );

    const fmt = new Intl.NumberFormat("en-GB", {
      style: "currency",
      currency: "GBP",
    });

    expect(screen.getByText("Test Owner")).toBeInTheDocument();
    expect(screen.getByText(fmt.format(100))).toBeInTheDocument();
    expect(screen.getByText(fmt.format(110))).toBeInTheDocument();
    expect(screen.getByText("10.00%")).toBeInTheDocument();
    expect(screen.getByText(fmt.format(200))).toBeInTheDocument();
    expect(screen.getByText(fmt.format(180))).toBeInTheDocument();
    expect(screen.getByText("-10.00%")).toBeInTheDocument();
  });

  it("disables Apply button until selections made", async () => {
    mockGetEvents.mockResolvedValueOnce([{ id: "e1", name: "Event 1" }]);
  it("disables Apply button until valid inputs provided", async () => {
    mockRunScenario.mockResolvedValueOnce([
      {
        owner: "Test Owner",
        baseline_total_value_gbp: 100,
        shocked_total_value_gbp: 110,
        delta_gbp: 10,
      } as ScenarioResult,
    ]);
    render(<ScenarioTester />);

    await screen.findByRole("combobox");
    const apply = screen.getByText("Apply");

    expect(apply).toBeDisabled();
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "e1" },
    });
    expect(apply).toBeDisabled();
    fireEvent.click(screen.getByLabelText("1d"));
    expect(apply).not.toBeDisabled();
    fireEvent.click(apply);
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

    fireEvent.click(screen.getByText("Apply"));

    expect(await screen.findByText("fail")).toBeInTheDocument();
  });
});

