import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, type Mock, beforeEach } from "vitest";

vi.mock("../api", () => ({ getInstrumentDetail: vi.fn() }));
import { getInstrumentDetail } from "../api";

class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(global as any).ResizeObserver = ResizeObserver;

import { InstrumentDetail } from "./InstrumentDetail";

describe("InstrumentDetail", () => {
  const mockGetInstrumentDetail = getInstrumentDetail as unknown as Mock;

  beforeEach(() => {
    mockGetInstrumentDetail.mockReset();
  });

  it("links to timeseries edit page", async () => {
    mockGetInstrumentDetail.mockResolvedValue({
      prices: [],
      positions: [],
      currency: null,
    });

    render(
      <MemoryRouter>
        <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />
      </MemoryRouter>,
    );
    const link = await screen.findByRole("link", { name: /edit/i });
    expect(link).toHaveAttribute("href", "/timeseries?ticker=ABC&exchange=L");
  });

  it("displays 7d and 30d changes", async () => {
    const prices = Array.from({ length: 30 }, (_, i) => ({
      date: `2024-01-${String(i + 1).padStart(2, "0")}`,
      close_gbp: 100,
    }));
    prices.push({ date: "2024-01-31", close_gbp: 130 });

    mockGetInstrumentDetail.mockResolvedValue({
      prices,
      positions: [],
      currency: null,
    });

    render(
      <MemoryRouter>
        <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/7d 30\.0%/)).toBeInTheDocument();
    expect(screen.getByText(/30d 30\.0%/)).toBeInTheDocument();
  });
});

