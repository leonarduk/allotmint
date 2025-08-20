import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import ScenarioTester from "./ScenarioTester";
import * as api from "../api";

vi.mock("../api");

const mockRunScenario = vi.mocked(api.runScenario);

describe("ScenarioTester page", () => {
  it("runs scenario and displays results", async () => {
    mockRunScenario.mockResolvedValueOnce([
      { ticker: "AAA", impact: 123 } as any,
    ]);

    render(<ScenarioTester />);

    fireEvent.change(screen.getByPlaceholderText("Ticker"), { target: { value: "AAA" } });
    fireEvent.change(screen.getByPlaceholderText("% Change"), { target: { value: "5" } });
    fireEvent.click(screen.getByText("Apply"));

    await waitFor(() => expect(mockRunScenario).toHaveBeenCalledWith("AAA", 5));
    expect(screen.getByText(/"ticker": "AAA"/)).toBeInTheDocument();
  });
});
