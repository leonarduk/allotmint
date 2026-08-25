import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("@/hooks/useInstrumentHistory", () => ({
  useInstrumentHistory: vi.fn(() => ({
    data: null,
    loading: false,
    error: null,
  })),
  getCachedInstrumentHistory: vi.fn(() => null),
  updateCachedInstrumentHistory: vi.fn(),
}));
import { useInstrumentHistory } from "@/hooks/useInstrumentHistory";
const mockUseInstrumentHistory = useInstrumentHistory as unknown as vi.Mock;
import { Sparkline } from "@/components/Sparkline";

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

  it("renders placeholder when fetch fails", () => {
    mockUseInstrumentHistory.mockReturnValueOnce({
      data: null,
      loading: false,
      error: new Error("fail"),
    });
    render(<Sparkline ticker="ABC" days={7} />);
    expect(screen.getByTestId("sparkline-empty")).toBeInTheDocument();
  });

  it("accepts batch-derived (mini-only) cache data instead of forcing a full-detail fetch", () => {
    render(<Sparkline ticker="ABC" days={7} />);
    // Dropping this flag silently reintroduces one full-detail request per
    // sparkline instead of sharing the table's single batch request.
    expect(mockUseInstrumentHistory).toHaveBeenCalledWith("ABC", 7, {
      acceptMiniOnly: true,
    });
  });
});
