import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import ScenarioTester from "./ScenarioTester";
import * as api from "../api";
import type { ScenarioResult } from "../types";

vi.mock("../api");

const mockRunScenario = vi.mocked(api.runScenario);

describe("ScenarioTester page", () => {
  beforeEach(() => {
    mockRunScenario.mockReset();
  });

  it("runs scenario and displays results in table", async () => {
    mockRunScenario.mockResolvedValueOnce([
      {
        owner: "Test Owner",
        baseline_total_value_gbp: 100,
        shocked_total_value_gbp: 110,
        delta_gbp: 10,
      } as ScenarioResult,
    ]);

    render(<ScenarioTester />);

    const apply = screen.getByText("Apply");
    expect(apply).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText("Ticker"), {
      target: { value: "AAA" },
    });
    fireEvent.change(screen.getByPlaceholderText("% Change"), {
      target: { value: "5" },
    });

    expect(apply).not.toBeDisabled();
    fireEvent.click(apply);

    await waitFor(() => expect(mockRunScenario).toHaveBeenCalledWith("AAA", 5));

    const fmt = new Intl.NumberFormat("en-GB", {
      style: "currency",
      currency: "GBP",
    });

    expect(screen.getByText("Test Owner")).toBeInTheDocument();
    expect(screen.getByText(fmt.format(100))).toBeInTheDocument();
    expect(screen.getByText(fmt.format(110))).toBeInTheDocument();
    expect(screen.getByText(fmt.format(10))).toBeInTheDocument();
  });

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
    const apply = screen.getByText("Apply");

    expect(apply).toBeDisabled();
    fireEvent.change(screen.getByPlaceholderText("Ticker"), {
      target: { value: "AAA" },
    });
    expect(apply).toBeDisabled();
    fireEvent.change(screen.getByPlaceholderText("% Change"), {
      target: { value: "abc" },
    });
    expect(apply).toBeDisabled();
    fireEvent.change(screen.getByPlaceholderText("% Change"), {
      target: { value: "10" },
    });
    expect(apply).not.toBeDisabled();
    fireEvent.click(apply);
    await waitFor(() => expect(mockRunScenario).toHaveBeenCalled());
    expect(screen.getByText("Test Owner")).toBeInTheDocument();
  });

  it("shows error message on failure", async () => {
    mockRunScenario.mockRejectedValueOnce(new Error("fail"));

    render(<ScenarioTester />);

    fireEvent.change(screen.getByPlaceholderText("Ticker"), {
      target: { value: "AAA" },
    });
    fireEvent.change(screen.getByPlaceholderText("% Change"), {
      target: { value: "5" },
    });

    fireEvent.click(screen.getByText("Apply"));

    expect(await screen.findByText("fail")).toBeInTheDocument();
  });
});

