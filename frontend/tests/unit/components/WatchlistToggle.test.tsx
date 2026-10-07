import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import WatchlistToggle from "@/components/WatchlistToggle";
import {
  DEFAULT_WATCHLIST_SYMBOLS,
  WATCHLIST_STORAGE_KEY,
} from "@/lib/watchlistStore";

describe("WatchlistToggle", () => {
  beforeEach(() => localStorage.clear());

  it("adds a ticker on top of the default list when nothing is stored yet", () => {
    render(<WatchlistToggle ticker="BP.L" />);
    const button = screen.getByRole("button", {
      name: i18n.t("watchlist.addTicker", { symbol: "BP.L" }),
    });
    expect(button).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(button);
    expect(localStorage.getItem(WATCHLIST_STORAGE_KEY)).toBe(
      `${DEFAULT_WATCHLIST_SYMBOLS},BP.L`,
    );
    expect(button).toHaveAttribute("aria-pressed", "true");
  });

  it("removes a watched ticker (case-insensitively) and keeps the rest", () => {
    localStorage.setItem(WATCHLIST_STORAGE_KEY, "AAA,bp.l");
    render(<WatchlistToggle ticker="BP.L" />);
    fireEvent.click(
      screen.getByRole("button", {
        name: i18n.t("watchlist.removeTicker", { symbol: "BP.L" }),
      }),
    );
    expect(localStorage.getItem(WATCHLIST_STORAGE_KEY)).toBe("AAA");
  });

  it("keeps every toggle for the same ticker in sync", () => {
    localStorage.setItem(WATCHLIST_STORAGE_KEY, "AAA");
    render(
      <>
        <WatchlistToggle ticker="BBB" />
        <WatchlistToggle ticker="BBB" />
      </>,
    );
    const [first, second] = screen.getAllByRole("button");
    fireEvent.click(first);
    expect(second).toHaveAttribute("aria-pressed", "true");
  });

  it("does not trigger the row's own click handler", () => {
    const onRowClick = vi.fn();
    render(
      <div onClick={onRowClick}>
        <WatchlistToggle ticker="AAA" />
      </div>,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(onRowClick).not.toHaveBeenCalled();
  });
});
