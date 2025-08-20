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
        total_value_estimate_gbp: 123,
        ticker: "AAA",
        impact: 123,
      } as unknown as ScenarioResult,
    ]);

    render(<ScenarioTester />);

    fireEvent.change(screen.getByPlaceholderText("Ticker"), { target: { value: "AAA" } });
    fireEvent.change(screen.getByPlaceholderText("% Change"), { target: { value: "5" } });
    fireEvent.click(screen.getByText("Apply"));

    await waitFor(() => expect(mockRunScenario).toHaveBeenCalledWith("AAA", 5));
    expect(screen.getByText(/"ticker": "AAA"/)).toBeInTheDocument();
  });
});
