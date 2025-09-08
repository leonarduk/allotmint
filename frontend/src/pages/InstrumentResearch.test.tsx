import { render, act } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import type { QuoteRow } from "../types";

let quotePromise: Promise<QuoteRow[]>;
let quoteSignal: AbortSignal | undefined;

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    getInstrumentDetail: vi.fn().mockResolvedValue({ positions: [] }),
    getScreener: vi.fn().mockResolvedValue([]),
    getNews: vi.fn().mockResolvedValue([]),
    getQuotes: vi.fn((symbols: string[], signal?: AbortSignal) => {
      quoteSignal = signal;
      quotePromise = new Promise<QuoteRow[]>((_, reject) => {
        signal?.addEventListener("abort", () => {
          const err: any = new Error("aborted");
          err.name = "AbortError";
          reject(err);
        });
      });
      return quotePromise;
    }),
  };
});

vi.mock("../hooks/useInstrumentHistory", () => ({
  useInstrumentHistory: () => ({ data: { "30": [] }, loading: false, error: null }),
}));

import InstrumentResearch from "./InstrumentResearch";

describe("InstrumentResearch page", () => {
  it("aborts quote fetch on unmount", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    const router = createMemoryRouter(
      [{ path: "/research/:ticker", element: <InstrumentResearch /> }],
      { initialEntries: ["/research/AAA"] },
    );
    const { unmount } = render(<RouterProvider router={router} />);
    await act(async () => {
      await Promise.resolve();
    }); // allow effect to run
    unmount();
    await expect(quotePromise).rejects.toMatchObject({ name: "AbortError" });
    expect(quoteSignal?.aborted).toBe(true);
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });
});

