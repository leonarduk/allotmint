import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { FilterBar, useFilterReducer } from "@/components/FilterBar";

const Wrapper = () => {
  const [state, dispatch] = useFilterReducer({ ticker: "AAA" });
  return <FilterBar state={state} dispatch={dispatch} />;
};

describe("FilterBar", () => {
  it("shows clear all when filter active", () => {
    render(<Wrapper />);
    expect(screen.getByText("Clear all")).toBeInTheDocument();
  });

  it("removes chip with keyboard", async () => {
    const user = userEvent.setup();
    render(<Wrapper />);
    const chip = screen.getByRole("button", { name: /Ticker: AAA/ });
    chip.focus();
    await user.keyboard("{Backspace}");
    expect(screen.queryByRole("button", { name: /Ticker: AAA/ })).toBeNull();
  });
});
