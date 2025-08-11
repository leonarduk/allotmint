import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

const navigate = vi.fn();

vi.mock("../api", () => ({
  getTradingSignals: vi.fn().mockResolvedValue([
    { ticker: "AAA", action: "BUY", reason: "Reason" },
  ]),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom",
  );
  return {
    ...actual,
    useNavigate: () => navigate,
  };
});

import { TradingAgent } from "./TradingAgent";
import { getTradingSignals } from "../api";

describe("TradingAgent page", () => {
  it("renders signals and navigates on ticker click", async () => {
    render(<TradingAgent />);
    expect(getTradingSignals).toHaveBeenCalled();
    const link = await screen.findByRole("link", { name: "AAA" });
    fireEvent.click(link);
    expect(navigate).toHaveBeenCalledWith("/instrument/AAA");
  });
});

