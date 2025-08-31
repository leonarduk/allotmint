import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Header } from "./Header";

describe("Header", () => {
  it("shows trade meter when data present", () => {
    render(<Header tradesThisMonth={3} tradesRemaining={17} />);
    expect(
      screen.getByText(/Trades this month: 3 \/ 20 \(Remaining: 17\)/)
    ).toBeInTheDocument();
  });

  it("renders nothing without data", () => {
    const { container } = render(<Header />);
    expect(container).toBeEmptyDOMElement();
  });
});
