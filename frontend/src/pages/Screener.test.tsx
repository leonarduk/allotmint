import { render, screen, fireEvent, waitFor } from "@testing-library/react";
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
  it("fetches all instruments by default and submits criteria", async () => {
    render(<Screener />);

    await waitFor(() =>
      expect(getScreener).toHaveBeenCalledWith([], expect.any(Object))
    );

    fireEvent.change(screen.getByLabelText(/Tickers/i), {
      target: { value: "AAA" },
    });
    fireEvent.change(screen.getByLabelText(/Max PEG/i), {
      target: { value: "2" },
    });

    fireEvent.click(screen.getByRole("button", { name: /run/i }));

    expect(await screen.findByText("AAA")).toBeInTheDocument();
    await waitFor(() =>
      expect(getScreener).toHaveBeenLastCalledWith(["AAA"], { peg_max: 2 })
    );
    expect(getScreener).toHaveBeenCalledTimes(2);
  });
});

