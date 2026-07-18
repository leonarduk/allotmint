import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { InstrumentHistoryChart } from "@/components/InstrumentHistoryChart";

describe("InstrumentHistoryChart", () => {
  it("shows an accessible loading skeleton instead of the chart while loading", () => {
    render(<InstrumentHistoryChart data={[]} loading />);

    expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
  });

  it("renders the chart once loading finishes", () => {
    render(
      <InstrumentHistoryChart
        data={[{ date: "2026-01-01", close_gbp: 100 }]}
        loading={false}
      />,
    );

    expect(screen.queryByRole("status", { name: /loading/i })).not.toBeInTheDocument();
  });
});
