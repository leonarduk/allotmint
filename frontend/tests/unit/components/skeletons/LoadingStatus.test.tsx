import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import LoadingStatus, { SLOW_LOAD_HINT_MS } from "@/components/skeletons/LoadingStatus";

describe("LoadingStatus", () => {
  beforeEach(() => {
    i18n.changeLanguage("en");
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("announces the label and hides the slow-load hint at first", () => {
    render(
      <LoadingStatus label="Loading things">
        <span>skeleton</span>
      </LoadingStatus>,
    );

    expect(screen.getByRole("status", { name: "Loading things" })).toBeInTheDocument();
    expect(screen.queryByTestId("loading-still-working")).toBeNull();
  });

  it("says the load is still going once it passes the threshold (#7215)", () => {
    render(
      <LoadingStatus label="Loading things">
        <span>skeleton</span>
      </LoadingStatus>,
    );

    act(() => {
      vi.advanceTimersByTime(SLOW_LOAD_HINT_MS - 1);
    });
    expect(screen.queryByTestId("loading-still-working")).toBeNull();

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(screen.getByTestId("loading-still-working")).toHaveTextContent(/still working/i);
  });

  it("never shows the hint when slowAfterMs is null", () => {
    render(
      <LoadingStatus label="Loading things" slowAfterMs={null}>
        <span>skeleton</span>
      </LoadingStatus>,
    );

    act(() => {
      vi.advanceTimersByTime(SLOW_LOAD_HINT_MS * 10);
    });
    expect(screen.queryByTestId("loading-still-working")).toBeNull();
  });
});
