import "@/setupTests";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { createInstance } from "i18next";
import type { ReactElement } from "react";
import en from "@/locales/en/translation.json";
import { describe, it, expect, vi, afterEach } from "vitest";
import { TimeseriesEdit } from "@/pages/TimeseriesEdit";
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

    fireEvent.change(screen.getByLabelText("Open"), {
      target: { value: "2" },
    });
    rows[0].Open = 2;

    fireEvent.click(screen.getByRole("button", { name: /add row/i }));
    expect(screen.getAllByLabelText("Date")).toHaveLength(2);
    const tickerInputs = screen.getAllByLabelText("Ticker");
    expect(tickerInputs[tickerInputs.length - 1]).toHaveValue("ABC.L");
    const sourceInputs = screen.getAllByLabelText("Source");
    expect(sourceInputs[sourceInputs.length - 1]).toHaveValue("Manual");

    fireEvent.click(screen.getAllByRole("button", { name: /delete/i })[1]);
    expect(screen.getAllByLabelText("Date")).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    expect(getTimeseries).toHaveBeenCalledWith("ABC", "L");
    expect(saveTimeseries).toHaveBeenCalledWith("ABC", "L", rows);
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
