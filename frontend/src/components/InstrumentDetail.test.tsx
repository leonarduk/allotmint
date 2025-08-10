import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";

vi.mock("../api", () => ({
  getInstrumentDetail: vi.fn().mockResolvedValue({
    prices: [],
    positions: [],
    currency: null,
  }),
}));

class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(global as any).ResizeObserver = ResizeObserver;

import { InstrumentDetail } from "./InstrumentDetail";

describe("InstrumentDetail", () => {
  it("links to timeseries edit page", async () => {
    render(
      <MemoryRouter>
        <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />
      </MemoryRouter>
    );
    const link = await screen.findByRole("link", { name: /edit/i });
    expect(link).toHaveAttribute("href", "/timeseries?ticker=ABC&exchange=L");
  });
});
