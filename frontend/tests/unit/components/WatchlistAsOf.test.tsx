import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { WatchlistAsOf } from "@/components/WatchlistAsOf";
import { WATCHLIST_META } from "@/data/watchlists";

describe("WatchlistAsOf", () => {
  it("shows the as-of date and source for a built-in watchlist", () => {
    render(<WatchlistAsOf name="FTSE 100" />);
    expect(screen.getByTestId("watchlist-as-of")).toHaveTextContent(
      /2026.*FTSE Russell/,
    );
  });

  it("formats the calendar date in UTC so it never shifts a day", () => {
    // Without timeZone: "UTC", runners west of UTC would show 8 Oct.
    const spy = vi.spyOn(Date.prototype, "toLocaleDateString");
    render(<WatchlistAsOf name="FTSE 100" />);
    expect(spy).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ timeZone: "UTC" }),
    );
    const [date] = spy.mock.contexts as Date[];
    expect(date.toISOString()).toBe(
      `${WATCHLIST_META["FTSE 100"].asOf}T00:00:00.000Z`,
    );
    spy.mockRestore();
  });

  it.each(["My Old List", "Portfolio", "toString"])(
    "renders nothing for unknown name %s (stale localStorage value)",
    (name) => {
      const { container } = render(<WatchlistAsOf name={name} />);
      expect(container).toBeEmptyDOMElement();
    },
  );
});
