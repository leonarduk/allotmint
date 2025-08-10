import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("../api", () => ({
  getTimeseries: vi.fn().mockResolvedValue([
    { Date: "2024-01-01", Open: 1, High: 1, Low: 1, Close: 1, Volume: 1 },
  ]),
  saveTimeseries: vi.fn().mockResolvedValue({ status: "ok", rows: 1 }),
}));

import { TimeseriesEdit } from "./TimeseriesEdit";
import { getTimeseries, saveTimeseries } from "../api";

describe("TimeseriesEdit page", () => {
  it("loads and saves CSV data", async () => {
    render(<TimeseriesEdit />);

    fireEvent.change(screen.getByLabelText(/Ticker/i), {
      target: { value: "ABC" },
    });

    fireEvent.click(screen.getByRole("button", { name: /load/i }));

    expect(await screen.findByText(/Loaded 1 rows/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    expect(saveTimeseries).toHaveBeenCalled();
    expect(getTimeseries).toHaveBeenCalledWith("ABC", "L");
  });
});
