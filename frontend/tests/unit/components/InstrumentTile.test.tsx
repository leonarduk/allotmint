import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("@/hooks/useInstrumentHistory", () => ({
  useInstrumentHistory: vi.fn(() => ({ data: null, loading: false, error: null })),
}));
import { useInstrumentHistory } from "@/hooks/useInstrumentHistory";
const mockUseInstrumentHistory = useInstrumentHistory as unknown as vi.Mock;
import { InstrumentTile } from "@/components/InstrumentTile";
import type { InstrumentSummary } from "@/types";

const instrument: InstrumentSummary = {
  ticker: "ABC.L",
  name: "Alpha PLC",
  units: 5,
  market_value_gbp: 100,
  gain_gbp: 10,
};

describe("InstrumentTile", () => {
  it("renders ticker and name", () => {
    render(<InstrumentTile instrument={instrument} />);
    expect(screen.getByText("ABC.L")).toBeInTheDocument();
    expect(screen.getByText("Alpha PLC")).toBeInTheDocument();
  });

  it("accepts batch-derived (mini-only) cache data instead of forcing a full-detail fetch", () => {
    render(<InstrumentTile instrument={instrument} days={30} />);
    // Dropping this flag silently reintroduces one full-detail request per
    // tile instead of sharing a preloaded batch response.
    expect(mockUseInstrumentHistory).toHaveBeenCalledWith("ABC.L", 30, {
      acceptMiniOnly: true,
    });
  });

  it("defaults to a 30-day window", () => {
    render(<InstrumentTile instrument={instrument} />);
    expect(mockUseInstrumentHistory).toHaveBeenCalledWith("ABC.L", 30, {
      acceptMiniOnly: true,
    });
  });
});
