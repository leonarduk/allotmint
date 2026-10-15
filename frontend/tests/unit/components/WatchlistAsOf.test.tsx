import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { WatchlistAsOf } from "@/components/WatchlistAsOf";

describe("WatchlistAsOf", () => {
  it("shows the as-of date and source for a built-in watchlist", () => {
    render(<WatchlistAsOf name="FTSE 100" />);
    expect(screen.getByTestId("watchlist-as-of")).toHaveTextContent(
      /2026.*FTSE Russell/,
    );
  });

  it.each(["My Old List", "Portfolio", "toString"])(
    "renders nothing for unknown name %s (stale localStorage value)",
    (name) => {
      const { container } = render(<WatchlistAsOf name={name} />);
      expect(container).toBeEmptyDOMElement();
    },
  );
});
