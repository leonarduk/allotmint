import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("../api", () => ({
  getScreener: vi.fn().mockResolvedValue([
    {
      ticker: "AAA",
      name: "Alpha",
      peg_ratio: 1,
      pe_ratio: 10,
      de_ratio: 0.5,
      fcf: 1000,
    },
  ]),
}));

import { Screener } from "./Screener";
import { getScreener } from "../api";

describe("Screener page", () => {
  it("submits criteria and renders results", async () => {
    render(<Screener />);

    fireEvent.change(screen.getByLabelText(/Tickers/i), {
      target: { value: "AAA" },
    });
    fireEvent.change(screen.getByLabelText(/Max PEG/i), {
      target: { value: "2" },
    });

    fireEvent.click(screen.getByRole("button", { name: /run/i }));

    expect(await screen.findByText("AAA")).toBeInTheDocument();
    expect(getScreener).toHaveBeenCalledWith(["AAA"], { peg_max: 2 });
  });
});

