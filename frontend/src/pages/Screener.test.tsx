import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("../api", () => ({
  getScreener: vi.fn().mockResolvedValue([
    { ticker: "AAA", name: "Alpha", peg_ratio: 1, pe_ratio: 10, de_ratio: 0.5, fcf: 1000 },
  ]),
}));

import { ScreenerPage } from "./Screener";

describe("ScreenerPage", () => {
  it("submits form and renders results", async () => {
    render(<ScreenerPage />);
    fireEvent.change(screen.getByLabelText(/Tickers/i), { target: { value: "AAA" } });
    fireEvent.click(screen.getByRole("button", { name: /Run/i }));
    expect(await screen.findByText("AAA")).toBeInTheDocument();
  });
});
