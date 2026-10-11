import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import WatchlistToggle from "@/components/WatchlistToggle";
import {
  DEFAULT_WATCHLIST_SYMBOLS,
  LEGACY_WATCHLIST_STORAGE_KEY,
  createWatchlist,
  readWatchlists,
  setActiveWatchlist,
} from "@/lib/watchlistStore";

function symbolsOf(name: string): string {
  const list = readWatchlists().lists.find((l) => l.name === name);
  return list ? list.symbols.join(",") : "<missing>";
}

function openPicker(ticker: string) {
  fireEvent.click(
    screen.getByRole("button", {
      name: i18n.t("watchlist.pickerLabel", { symbol: ticker }),
    }),
  );
}

describe("WatchlistToggle", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it("asks which list rather than adding straight away", () => {
    render(<WatchlistToggle ticker="BP.L" />);
    openPicker("BP.L");

    expect(
      screen.getByRole("checkbox", { name: "My watchlist" }),
    ).not.toBeChecked();
    expect(symbolsOf("My watchlist")).toBe(DEFAULT_WATCHLIST_SYMBOLS);
  });

  it("adds to the chosen list only, on top of the defaults if never edited", () => {
    render(<WatchlistToggle ticker="BP.L" />);
    createWatchlist("Miners");
    // The star targets whichever list is ticked, not the active one.
    setActiveWatchlist(readWatchlists().lists[0].id);
    openPicker("BP.L");

    fireEvent.click(screen.getByRole("checkbox", { name: "Miners" }));

    expect(symbolsOf("Miners")).toBe("BP.L");
    expect(symbolsOf("My watchlist")).toBe(DEFAULT_WATCHLIST_SYMBOLS);
    expect(
      screen.getByRole("button", {
        name: i18n.t("watchlist.pickerLabel", { symbol: "BP.L" }),
      }),
    ).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByRole("checkbox", { name: "My watchlist" }));
    expect(symbolsOf("My watchlist")).toBe(`${DEFAULT_WATCHLIST_SYMBOLS},BP.L`);
  });

  it("removes a watched ticker (case-insensitively) and keeps the rest", () => {
    localStorage.setItem(LEGACY_WATCHLIST_STORAGE_KEY, "AAA,bp.l");
    render(<WatchlistToggle ticker="BP.L" />);
    openPicker("BP.L");

    const box = screen.getByRole("checkbox", { name: "My watchlist" });
    expect(box).toBeChecked();
    fireEvent.click(box);

    expect(symbolsOf("My watchlist")).toBe("AAA");
  });

  it("creates a new list containing the ticker", () => {
    vi.spyOn(window, "prompt").mockReturnValue("  Banks  ");
    render(<WatchlistToggle ticker="HSBA.L" />);
    openPicker("HSBA.L");

    fireEvent.click(screen.getByRole("button", { name: "New watchlist…" }));

    expect(symbolsOf("Banks")).toBe("HSBA.L");
    expect(screen.getByRole("checkbox", { name: "Banks" })).toBeChecked();
  });

  it("refuses a duplicate list name", () => {
    vi.spyOn(window, "prompt").mockReturnValue("my watchlist");
    const alert = vi.spyOn(window, "alert").mockImplementation(() => {});
    render(<WatchlistToggle ticker="HSBA.L" />);
    openPicker("HSBA.L");

    fireEvent.click(screen.getByRole("button", { name: "New watchlist…" }));

    expect(alert).toHaveBeenCalled();
    expect(readWatchlists().lists).toHaveLength(1);
  });

  it("keeps every toggle for the same ticker in sync", () => {
    localStorage.setItem(LEGACY_WATCHLIST_STORAGE_KEY, "AAA");
    render(
      <>
        <WatchlistToggle ticker="BBB" />
        <WatchlistToggle ticker="BBB" />
      </>,
    );
    const [first, second] = screen.getAllByRole("button");
    fireEvent.click(first);
    fireEvent.click(screen.getByRole("checkbox", { name: "My watchlist" }));
    expect(second).toHaveAttribute("aria-pressed", "true");
  });

  it("closes on Escape", () => {
    render(<WatchlistToggle ticker="AAA" />);
    openPicker("AAA");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("does not trigger the row's own click handler", () => {
    const onRowClick = vi.fn();
    render(
      <div onClick={onRowClick}>
        <WatchlistToggle ticker="AAA" />
      </div>,
    );
    openPicker("AAA");
    fireEvent.click(screen.getByRole("checkbox", { name: "My watchlist" }));
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it("labels the button variant with the number of lists it is on", () => {
    localStorage.setItem(LEGACY_WATCHLIST_STORAGE_KEY, "AAA");
    createWatchlist("Second", ["AAA"]);
    render(<WatchlistToggle ticker="AAA" variant="button" />);
    expect(
      screen.getByRole("button", { name: "On 2 watchlists…" }),
    ).toBeInTheDocument();
  });
});
