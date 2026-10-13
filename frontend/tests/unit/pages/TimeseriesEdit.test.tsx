import "@/setupTests";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { createInstance } from "i18next";
import type { ReactElement } from "react";
import en from "@/locales/en/translation.json";
import { describe, it, expect, vi, afterEach } from "vitest";
import { TIMESERIES_PAGE_SIZE, TimeseriesEdit } from "@/pages/TimeseriesEdit";
import {
  getTimeseries,
  moveTimeseries,
  saveTimeseries,
  searchInstruments,
} from "@/api";

vi.mock("@/api", () => ({
  getTimeseries: vi.fn(),
  moveTimeseries: vi.fn(),
  saveTimeseries: vi.fn().mockResolvedValue({ status: "ok", rows: 1 }),
  searchInstruments: vi.fn().mockResolvedValue([]),
  getInstrumentMetadata: vi.fn().mockResolvedValue(null),
}));

function renderWithI18n(ui: ReactElement) {
  const i18n = createInstance();
  i18n.use(initReactI18next).init({
    lng: "en",
    resources: { en: { translation: en } },
  });
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("TimeseriesEdit page", () => {
  it("loads, edits, adds and deletes rows, then saves", async () => {
    const rows = [
      { Date: "2024-01-01", Open: 1, High: 1, Low: 1, Close: 1, Volume: 1 },
    ];
    const getTimeseriesMock = getTimeseries as unknown as vi.Mock;
    getTimeseriesMock.mockResolvedValue(rows);
    renderWithI18n(<TimeseriesEdit />);

    expect(
      (screen.getByLabelText(/Exchange/i) as HTMLSelectElement).value,
    ).toBe("L");

    fireEvent.change(screen.getByLabelText(/Ticker/i), {
      target: { value: "ABC" },
    });

    fireEvent.click(screen.getByRole("button", { name: /load/i }));

    expect(await screen.findByDisplayValue("2024-01-01")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Open on 2024-01-01"), {
      target: { value: "2" },
    });
    rows[0].Open = 2;

    fireEvent.click(screen.getByRole("button", { name: /add row/i }));
    expect(screen.getAllByLabelText(/^Date (on|for)/)).toHaveLength(2);
    expect(screen.getByLabelText("Ticker for undated row 2")).toHaveValue(
      "ABC.L",
    );
    expect(screen.getByLabelText("Source for undated row 2")).toHaveValue(
      "Manual",
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Delete for undated row 2" }),
    );
    expect(screen.getAllByLabelText(/^Date (on|for)/)).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    expect(getTimeseries).toHaveBeenCalledWith("ABC", "L");
    expect(saveTimeseries).toHaveBeenCalledWith("ABC", "L", rows);
  });

  it("gives the Ticker, Exchange, Start and End controls accessible names", () => {
    renderWithI18n(<TimeseriesEdit />);
    expect(screen.getByRole("combobox", { name: "Ticker" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Exchange" })).toHaveValue("L");
    expect(screen.getByLabelText("Start date")).toHaveAttribute("type", "date");
    expect(screen.getByLabelText("End date")).toHaveAttribute("type", "date");
  });

  it("renders a bounded page of a long series and still saves every row (#10825)", async () => {
    const start = Date.UTC(2013, 0, 1);
    const rows = Array.from({ length: 3383 }, (_, i) => ({
      Date: new Date(start + i * 86_400_000).toISOString().slice(0, 10),
      Open: i,
      High: i,
      Low: i,
      Close: i,
      Volume: i,
      Ticker: "VHYL.L",
      Source: "Feed",
    }));
    (getTimeseries as unknown as vi.Mock).mockResolvedValue(rows);
    renderWithI18n(<TimeseriesEdit />);
    fireEvent.change(screen.getByLabelText("Ticker"), {
      target: { value: "VHYL" },
    });
    fireEvent.click(screen.getByRole("button", { name: /load/i }));
    expect(await screen.findByText("Loaded 3383 rows")).toBeInTheDocument();

    const grid = screen.getByRole("table", { name: "Rows" });
    expect(grid.querySelectorAll("input")).toHaveLength(
      TIMESERIES_PAGE_SIZE * 8,
    );
    expect(grid.querySelectorAll("input").length).toBeLessThan(500);
    // Newest first by default.
    const newest = rows[rows.length - 1].Date;
    expect(screen.getByLabelText(`Close on ${newest}`)).toBeInTheDocument();
    expect(
      screen.getByText(`Page 1 of 68 (rows 1–50 of 3383)`),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    const offPageDate = rows[rows.length - 51].Date;
    expect(screen.queryByLabelText(`Close on ${newest}`)).toBeNull();
    fireEvent.change(screen.getByLabelText(`Close on ${offPageDate}`), {
      target: { value: "999" },
    });
    // Edit survives paging away and back.
    fireEvent.click(screen.getByRole("button", { name: "Previous page" }));
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByLabelText(`Close on ${offPageDate}`)).toHaveValue(999);

    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    const saved = (saveTimeseries as unknown as vi.Mock).mock.calls[0][2];
    expect(saved).toHaveLength(3383);
    expect(saved.find((r: { Date: string }) => r.Date === offPageDate).Close).toBe(
      999,
    );
  });

  async function loadDailySeries(length: number) {
    const start = Date.UTC(2013, 0, 1);
    const rows = Array.from({ length }, (_, i) => ({
      Date: new Date(start + i * 86_400_000).toISOString().slice(0, 10),
      Close: i,
    }));
    (getTimeseries as unknown as vi.Mock).mockResolvedValue(rows);
    renderWithI18n(<TimeseriesEdit />);
    fireEvent.change(screen.getByLabelText("Ticker"), {
      target: { value: "ABC" },
    });
    fireEvent.click(screen.getByRole("button", { name: /load/i }));
    expect(await screen.findByText(`Loaded ${length} rows`)).toBeInTheDocument();
    return rows;
  }

  it("jumps to the page holding a newly added row", async () => {
    await loadDailySeries(120);
    fireEvent.click(screen.getByRole("button", { name: /add row/i }));
    expect(
      screen.getByText("Page 3 of 3 (rows 101–121 of 121)"),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Date for undated row 121")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Previous page" }));
    expect(
      screen.getByText("Page 2 of 3 (rows 51–100 of 121)"),
    ).toBeInTheDocument();
  });

  it("keeps the current page when adding a row under a date filter", async () => {
    await loadDailySeries(120);
    fireEvent.change(screen.getByLabelText("Start date"), {
      target: { value: "2013-01-01" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    fireEvent.click(screen.getByRole("button", { name: /add row/i }));
    // The undated row is hidden by the filter, so the page doesn't move.
    expect(
      screen.getByText("Page 2 of 3 (rows 51–100 of 120)"),
    ).toBeInTheDocument();
  });

  it("returns to page 1 when the sort or date range changes", async () => {
    await loadDailySeries(120);
    const nav = screen.getByRole("navigation", { name: "Row pages" });
    expect(nav).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    fireEvent.change(screen.getByLabelText("Sort"), {
      target: { value: "asc" },
    });
    expect(
      screen.getByText("Page 1 of 3 (rows 1–50 of 120)"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    fireEvent.change(screen.getByLabelText("End date"), {
      target: { value: "2030-01-01" },
    });
    expect(
      screen.getByText("Page 1 of 3 (rows 1–50 of 120)"),
    ).toBeInTheDocument();
  });

  it("falls back to the new last page when a delete removes it", async () => {
    const rows = await loadDailySeries(101);
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(
      screen.getByText("Page 3 of 3 (rows 101–101 of 101)"),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: `Delete on ${rows[0].Date}` }),
    );
    expect(
      screen.getByText("Page 2 of 2 (rows 51–100 of 100)"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Previous page" }));
    expect(
      screen.getByText("Page 1 of 2 (rows 1–50 of 100)"),
    ).toBeInTheDocument();
  });

  it("stays on the current page after deleting a row", async () => {
    const rows = await loadDailySeries(120);
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    const target = rows[rows.length - 51].Date;
    fireEvent.click(screen.getByRole("button", { name: `Delete on ${target}` }));
    expect(screen.queryByLabelText(`Close on ${target}`)).toBeNull();
    expect(
      screen.getByText("Page 2 of 3 (rows 51–100 of 119)"),
    ).toBeInTheDocument();
  });

  it("prefills ticker and exchange from URL", async () => {
    const getTimeseriesMock = getTimeseries as unknown as vi.Mock;
    getTimeseriesMock.mockResolvedValue([]);
    window.history.pushState({}, "", "/timeseries?ticker=XYZ&exchange=DE");
    renderWithI18n(<TimeseriesEdit />);
    expect(await screen.findByDisplayValue("XYZ")).toBeInTheDocument();
    expect(await screen.findByDisplayValue("DE")).toBeInTheDocument();
    window.history.pushState({}, "", "/");
  });

  it("suggests tickers and updates value when one is selected", async () => {
    const getTimeseriesMock = getTimeseries as unknown as vi.Mock;
    getTimeseriesMock.mockResolvedValue([]);
    const searchMock = searchInstruments as unknown as vi.Mock;
    searchMock.mockResolvedValue([{ ticker: "AAA", name: "AAA Corp" }]);
    renderWithI18n(<TimeseriesEdit />);
    const input = screen.getByLabelText(/Ticker/i);
    fireEvent.change(input, { target: { value: "AA" } });
    await new Promise((r) => setTimeout(r, 350));
    expect(await screen.findByText("AAA — AAA Corp")).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "AAA" } });
    expect(input).toHaveValue("AAA");
  });

  it("does not emit duplicate-key warnings for duplicate suggestion tickers (#6505)", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const getTimeseriesMock = getTimeseries as unknown as vi.Mock;
    getTimeseriesMock.mockResolvedValue([]);
    const searchMock = searchInstruments as unknown as vi.Mock;
    searchMock.mockResolvedValue([
      { ticker: "CASH", name: "Cash GBP" },
      { ticker: "CASH", name: "Cash L" },
    ]);
    renderWithI18n(<TimeseriesEdit />);
    const input = screen.getByLabelText(/Ticker/i);
    fireEvent.change(input, { target: { value: "CA" } });
    await new Promise((r) => setTimeout(r, 350));
    expect(await screen.findByText("CASH — Cash GBP")).toBeInTheDocument();
    expect(screen.getAllByText(/CASH —/)).toHaveLength(2);
    const keyWarnings = errorSpy.mock.calls.filter((args) =>
      String(args[0]).includes("same key"),
    );
    expect(keyWarnings).toEqual([]);
    errorSpy.mockRestore();
  });

  it("enables Move after an empty load and surfaces an actionable error", async () => {
    const getTimeseriesMock = getTimeseries as unknown as vi.Mock;
    getTimeseriesMock.mockResolvedValue([]);
    const moveTimeseriesMock = moveTimeseries as unknown as vi.Mock;
    const err = new Error("backend detail") as Error & { status?: number };
    err.status = 404;
    moveTimeseriesMock.mockRejectedValue(err);

    renderWithI18n(<TimeseriesEdit />);
    fireEvent.change(screen.getByLabelText(/Ticker/i), {
      target: { value: "ABC" },
    });
    fireEvent.click(screen.getByRole("button", { name: /load/i }));

    expect(await screen.findByText(/no data exists/i)).toBeInTheDocument();

    const moveButton = screen.getByRole("button", { name: /move to l/i });
    expect(moveButton).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Exchange/i), {
      target: { value: "N" },
    });
    const moveToN = screen.getByRole("button", { name: /move to n/i });
    expect(moveToN).toBeEnabled();
    fireEvent.click(moveToN);

    expect(await screen.findByText(/correct the holding/i)).toBeInTheDocument();
    expect(moveTimeseries).toHaveBeenCalledWith("ABC", "L", "N");
  });
});
