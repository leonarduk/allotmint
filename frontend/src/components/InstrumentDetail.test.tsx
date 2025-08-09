import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal("ResizeObserver", ResizeObserverMock);

vi.mock("../api", () => ({
  getInstrumentDetail: vi.fn(() =>
    Promise.resolve({ prices: [], positions: [], currency: "GBP" })
  ),
}));

import { InstrumentDetail } from "./InstrumentDetail";

describe("InstrumentDetail", () => {
  it("renders ticker info", async () => {
    render(
      <MemoryRouter>
        <InstrumentDetail
          ticker="ABC"
          name="ABC Corp"
          currency="GBP"
          instrument_type="Equity"
          onClose={() => {}}
        />
      </MemoryRouter>
    );
    expect(
      await screen.findByText("ABC • GBP • Equity")
    ).toBeInTheDocument();
  });
});
