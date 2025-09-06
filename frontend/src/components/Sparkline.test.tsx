import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Sparkline } from "./Sparkline";

describe("Sparkline", () => {
  it("renders polyline points based on data", () => {
    render(<Sparkline data={[1, 3, 2]} width={100} height={20} />);
    const svg = screen.getByTestId("sparkline");
    const poly = svg.querySelector("polyline");
    expect(poly).not.toBeNull();
    expect(poly).toHaveAttribute("points", "0,20 50,0 100,10");
  });

  it("renders empty svg when no data provided", () => {
    render(<Sparkline data={[]} />);
    expect(screen.getByTestId("sparkline-empty")).toBeInTheDocument();
  });
});
