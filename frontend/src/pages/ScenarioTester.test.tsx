import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import ScenarioTester from "./ScenarioTester";
import * as api from "../api";
import type { ScenarioResult } from "../types";

vi.mock("../api");

const mockRunScenario = vi.mocked(api.runScenario);

describe("ScenarioTester page", () => {
  it("runs scenario and displays results", async () => {
    mockRunScenario.mockResolvedValueOnce([
      {
        owner: "Test Owner",
        baseline_total_value_gbp: 1000,
        shocked_total_value_gbp: 950,
        delta_gbp: -50,
      } as ScenarioResult,
    ]);

    render(<ScenarioTester />);

    fireEvent.change(screen.getByPlaceholderText("Ticker"), { target: { value: "AAA" } });
    fireEvent.change(screen.getByPlaceholderText("% Change"), { target: { value: "5" } });
    fireEvent.click(screen.getByText("Apply"));

    await waitFor(() => expect(mockRunScenario).toHaveBeenCalledWith("AAA", 5));

    const pre = await screen.findByText(/Test Owner/);
    const data = JSON.parse(pre.textContent || "[]");
    const result = data[0] as ScenarioResult;
    expect(typeof result.baseline_total_value_gbp).toBe("number");
    expect(typeof result.shocked_total_value_gbp).toBe("number");
    expect(typeof result.delta_gbp).toBe("number");
  });

  it("shows error message on failure", async () => {
    mockRunScenario.mockRejectedValueOnce(new Error("fail"));

    render(<ScenarioTester />);

    fireEvent.change(screen.getByPlaceholderText("Ticker"), { target: { value: "AAA" } });
    fireEvent.change(screen.getByPlaceholderText("% Change"), { target: { value: "5" } });
    fireEvent.click(screen.getByText("Apply"));

    expect(await screen.findByText("fail")).toBeInTheDocument();
  });
});
