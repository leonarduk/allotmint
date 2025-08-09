import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("../api", () => ({
  getScreener: vi.fn().mockResolvedValue([
    { ticker: "AAA", name: "Alpha", peg_ratio: 1, pe_ratio: 10, de_ratio: 0.5, fcf: 1000 },
  ]),
}));

import { ScreenerPage } from "./ScreenerPage";

describe("ScreenerPage", () => {
  it("renders screener results", async () => {
    render(<ScreenerPage />);
    expect(await screen.findByText("AAA")).toBeInTheDocument();
  });
});
