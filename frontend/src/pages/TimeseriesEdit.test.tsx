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
  it.skip("loads, edits, adds and deletes rows, then saves", async () => {
    vi.clearAllMocks();
    render(<TimeseriesEdit />);

    fireEvent.change(screen.getByLabelText(/Ticker/i), {
      target: { value: "ABC" },
    });

    fireEvent.click(screen.getByRole("button", { name: /load/i }));

    expect(await screen.findByDisplayValue("2024-01-01")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Open"), {
      target: { value: "2" },
    });

    fireEvent.click(screen.getByRole("button", { name: /add row/i }));
    expect(screen.getAllByLabelText("Date")).toHaveLength(2);

    fireEvent.click(screen.getAllByRole("button", { name: /delete/i })[1]);
    expect(screen.getAllByLabelText("Date")).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    expect(getTimeseries).toHaveBeenCalledWith("ABC", "L");
    expect(saveTimeseries).toHaveBeenCalledWith("ABC", "L", [
      {
        Date: "2024-01-01",
        Open: 2,
        High: 1,
        Low: 1,
        Close: 1,
        Volume: 1,
      },
    ]);
  });

  it("prefills ticker and exchange from URL", async () => {
    window.history.pushState({}, "", "/timeseries?ticker=XYZ&exchange=US");
    render(<TimeseriesEdit />);
    expect(await screen.findByDisplayValue("XYZ")).toBeInTheDocument();
    expect(await screen.findByDisplayValue("US")).toBeInTheDocument();
    window.history.pushState({}, "", "/");
  });
});
