import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, type Mock, beforeEach } from "vitest";
import { cloneElement, isValidElement } from "react";
import i18n from "@/i18n";

vi.mock("@/api", () => ({
  getInstrumentDetail: vi.fn(),
  getInstrumentIntraday: vi.fn(),
  getInstrumentFxSplit: vi.fn(() => Promise.resolve({ applicable: false })),
  getTransactions: vi.fn(() => Promise.resolve([])),
  searchInstruments: vi.fn(() => Promise.resolve([])),
}));

// jsdom gives ResponsiveContainer a 0x0 parent, so recharts would draw nothing.
vi.mock("recharts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("recharts")>();
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) =>
      isValidElement(children)
        ? cloneElement(
            children as React.ReactElement<Record<string, unknown>>,
            {
              width: 800,
              height: 260,
            },
          )
        : children,
  };
});

import { getInstrumentDetail } from "@/api";
import { InstrumentDetail } from "@/components/InstrumentDetail";

class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserver as never;

const series = (start: number) => ({
  prices: [
    { date: "2024-01-01", close: start, close_gbp: start },
    { date: "2024-01-02", close: start * 1.1, close_gbp: start * 1.1 },
  ],
  positions: [],
  currency: "GBP",
});

const lineCount = (container: HTMLElement) =>
  container.querySelectorAll(".recharts-line").length;

describe("InstrumentDetail series comparison", () => {
  const mockDetail = getInstrumentDetail as unknown as Mock;

  beforeEach(() => {
    mockDetail.mockReset();
    mockDetail.mockImplementation((ticker: string) =>
      Promise.resolve(series(ticker === "ABC.L" ? 100 : 20)),
    );
    i18n.changeLanguage("en");
  });

  const renderDetail = () =>
    render(
      <MemoryRouter>
        <InstrumentDetail ticker="ABC.L" name="ABC" variant="standalone" />
      </MemoryRouter>,
    );

  it("overlays an added ticker and fetches it for the current range", async () => {
    const { container } = renderDetail();

    await userEvent.type(
      await screen.findByLabelText(/Compare with/),
      "xyz.l{Enter}",
    );

    expect(mockDetail).toHaveBeenCalledWith(
      "XYZ.L",
      365,
      expect.any(AbortSignal),
    );
    expect(await screen.findByText("ABC.L")).toBeInTheDocument();
    await vi.waitFor(() => expect(lineCount(container)).toBe(2));
    expect(screen.queryByLabelText("Bollinger Bands")).not.toBeInTheDocument();
  });

  it("goes back to the price chart when the comparison is removed", async () => {
    renderDetail();
    await userEvent.type(
      await screen.findByLabelText(/Compare with/),
      "XYZ.L{Enter}",
    );

    await userEvent.click(await screen.findByLabelText("Remove XYZ.L"));

    expect(await screen.findByLabelText("Bollinger Bands")).toBeInTheDocument();
  });

  it("ignores the page's own ticker", async () => {
    renderDetail();
    await userEvent.type(
      await screen.findByLabelText(/Compare with/),
      "abc.l{Enter}",
    );

    expect(screen.queryByLabelText("Remove ABC.L")).not.toBeInTheDocument();
  });
});
