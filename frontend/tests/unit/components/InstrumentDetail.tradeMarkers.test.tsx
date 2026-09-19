import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, type Mock, beforeEach } from "vitest";
import { cloneElement, isValidElement } from "react";
import i18n from "@/i18n";
import {
  BUY_MARKER_COLOR,
  SELL_MARKER_COLOR,
} from "@/components/instrumentTradeMarkers";

vi.mock("@/api", () => ({
  getInstrumentDetail: vi.fn(),
  getInstrumentIntraday: vi.fn(),
  getTransactions: vi.fn(),
}));

// ResponsiveContainer measures its parent, which is always 0x0 in jsdom, so
// recharts renders nothing at all.  Giving the chart an explicit size is what
// lets these tests assert on the reference lines that actually reach the SVG.
vi.mock("recharts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("recharts")>();
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) =>
      isValidElement(children)
        ? cloneElement(children as React.ReactElement<Record<string, unknown>>, {
            width: 800,
            height: 220,
          })
        : children,
  };
});

import { getInstrumentDetail, getTransactions } from "@/api";
import { InstrumentDetail } from "@/components/InstrumentDetail";

class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserver as never;

const PRICES = [
  { date: "2024-01-01", close: 100, close_gbp: 100 },
  { date: "2024-01-02", close: 101, close_gbp: 101 },
  { date: "2024-01-03", close: 102, close_gbp: 102 },
  { date: "2024-01-04", close: 103, close_gbp: 103 },
];

const referenceLineStrokes = (container: HTMLElement): string[] =>
  Array.from(container.querySelectorAll(".recharts-reference-line line")).map(
    (el) => el.getAttribute("stroke") ?? "",
  );

describe("InstrumentDetail trade marker rendering", () => {
  const mockGetInstrumentDetail = getInstrumentDetail as unknown as Mock;
  const mockGetTransactions = getTransactions as unknown as Mock;

  beforeEach(() => {
    mockGetInstrumentDetail.mockReset();
    mockGetTransactions.mockReset();
    mockGetInstrumentDetail.mockResolvedValue({
      prices: PRICES,
      positions: [],
      currency: "GBP",
    });
    mockGetTransactions.mockResolvedValue([]);
    i18n.changeLanguage("en");
  });

  it("draws a green line for a buy and a red line for a sell", async () => {
    mockGetTransactions.mockResolvedValue([
      {
        owner: "alice",
        account: "isa",
        id: "buy-1",
        date: "2024-01-02",
        ticker: "ABC.L",
        type: "BUY",
        shares: 10,
        price_gbp: 101,
      },
      {
        owner: "alice",
        account: "isa",
        id: "sell-1",
        date: "2024-01-04",
        ticker: "ABC.L",
        type: "SELL",
        shares: 5,
        price_gbp: 103,
      },
    ]);

    const { container } = render(
      <MemoryRouter>
        <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />
      </MemoryRouter>,
    );

    await userEvent.click(await screen.findByLabelText("Trade markers"));

    await vi.waitFor(() => {
      expect(referenceLineStrokes(container)).toEqual([
        BUY_MARKER_COLOR,
        SELL_MARKER_COLOR,
      ]);
    });
  });

  it("draws nothing while the overlay is switched off", async () => {
    mockGetTransactions.mockResolvedValue([
      {
        owner: "alice",
        account: "isa",
        id: "buy-1",
        date: "2024-01-02",
        ticker: "ABC.L",
        type: "BUY",
      },
    ]);

    const { container } = render(
      <MemoryRouter>
        <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />
      </MemoryRouter>,
    );

    await screen.findByLabelText("Trade markers");

    expect(referenceLineStrokes(container)).toEqual([]);
  });

  it("removes the lines again when the overlay is switched back off", async () => {
    mockGetTransactions.mockResolvedValue([
      {
        owner: "alice",
        account: "isa",
        id: "buy-1",
        date: "2024-01-02",
        ticker: "ABC.L",
        type: "BUY",
      },
    ]);

    const { container } = render(
      <MemoryRouter>
        <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />
      </MemoryRouter>,
    );

    const toggle = await screen.findByLabelText("Trade markers");
    await userEvent.click(toggle);
    await vi.waitFor(() => {
      expect(referenceLineStrokes(container)).toHaveLength(1);
    });

    await userEvent.click(toggle);

    expect(referenceLineStrokes(container)).toEqual([]);
  });

  it("ignores trades in other instruments and outside the charted range", async () => {
    mockGetTransactions.mockResolvedValue([
      {
        owner: "alice",
        account: "isa",
        id: "other-instrument",
        date: "2024-01-02",
        ticker: "XYZ.L",
        type: "BUY",
      },
      {
        owner: "alice",
        account: "isa",
        id: "out-of-range",
        date: "2019-01-02",
        ticker: "ABC.L",
        type: "BUY",
      },
      {
        owner: "alice",
        account: "isa",
        id: "dividend",
        date: "2024-01-03",
        ticker: "ABC.L",
        type: "DIVIDEND",
      },
    ]);

    const { container } = render(
      <MemoryRouter>
        <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />
      </MemoryRouter>,
    );

    await userEvent.click(await screen.findByLabelText("Trade markers"));

    await vi.waitFor(() => {
      expect(screen.getByLabelText("Trade markers")).toBeChecked();
    });
    expect(referenceLineStrokes(container)).toEqual([]);
  });

  it("collapses a heavily traded instrument to the first and last line per side", async () => {
    // 20 trades across 4 charted dates: far past the marker cap.
    mockGetTransactions.mockResolvedValue(
      Array.from({ length: 20 }, (_, i) => ({
        owner: "alice",
        account: "isa",
        id: `t${i}`,
        date: PRICES[i % PRICES.length].date,
        ticker: "ABC.L",
        type: i % 2 === 0 ? "BUY" : "SELL",
      })),
    );

    const { container } = render(
      <MemoryRouter>
        <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />
      </MemoryRouter>,
    );

    await userEvent.click(await screen.findByLabelText("Trade markers"));

    await vi.waitFor(() => {
      const strokes = referenceLineStrokes(container);
      expect(strokes).toHaveLength(4);
      expect(strokes.filter((s) => s === BUY_MARKER_COLOR)).toHaveLength(2);
      expect(strokes.filter((s) => s === SELL_MARKER_COLOR)).toHaveLength(2);
    });
  });
});
