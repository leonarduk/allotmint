import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { TopMoversPage, computeMoversLoading } from "@/components/TopMoversPage";
import type { OpportunityEntry, TradingSignal } from "@/types";
import enTranslation from "@/locales/en/translation.json";

vi.mock("@/data/watchlists", () => ({
  WATCHLISTS: { "FTSE 100": ["AAA", "BBB"] },
}));

const signal: TradingSignal = {
  ticker: "AAA",
  action: "BUY",
  reason: "go long",
};

const groupEntries: OpportunityEntry[] = [
  {
    ticker: "AAA",
    name: "AAA",
    change_pct: 5,
    market_value_gbp: 100,
    instrument_type: "stock",
    side: "gainers",
    signal,
  },
  {
    ticker: "BBB",
    name: "BBB",
    change_pct: -2,
    market_value_gbp: 50,
    side: "losers",
  },
];

const watchlistEntries: OpportunityEntry[] = [
  {
    ticker: "AAA",
    name: "AAA",
    change_pct: 5,
    side: "gainers",
  },
  {
    ticker: "BBB",
    name: "BBB",
    change_pct: -2,
    side: "losers",
  },
];

const mockGetOpportunities = vi.fn((opts: { group?: string; tickers?: string[] }) => {
  if (opts.group === "all") {
    return Promise.resolve({
      entries: groupEntries,
      signals: [signal],
      context: { source: "group", group: "all", days: 1, anomalies: [] },
    });
  }
  return Promise.resolve({
    entries: watchlistEntries,
    signals: [],
    context: { source: "watchlist", tickers: opts.tickers ?? [], days: 1, anomalies: [] },
  });
});

const mockGetGroupInstruments = vi.fn(() =>
  Promise.resolve([
    {
      ticker: "AAA",
      name: "AAA",
      market_value_gbp: 100,
      gain_gbp: 0,
      units: 1,
      currency: "GBP",
    },
    {
      ticker: "BBB",
      name: "BBB",
      market_value_gbp: 50,
      gain_gbp: 0,
      units: 1,
      currency: "GBP",
    },
  ]),
);

vi.mock("@/api", () => ({
  getOpportunities: (
    ...args: Parameters<typeof mockGetOpportunities>
  ) => mockGetOpportunities(...args),
  getGroupInstruments: (
    ...args: Parameters<typeof mockGetGroupInstruments>
  ) => mockGetGroupInstruments(...args),
}));

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  mockGetOpportunities.mockImplementation((opts) => {
    if (opts.group === "all") {
      return Promise.resolve({
        entries: groupEntries,
        signals: [signal],
        context: { source: "group", group: "all", days: 1, anomalies: [] },
      });
    }
    return Promise.resolve({
      entries: watchlistEntries,
      signals: [],
      context: {
        source: "watchlist",
        tickers: opts.tickers ?? [],
        days: 1,
        anomalies: [],
      },
    });
  });
});

vi.mock("@/components/InstrumentDetail", () => ({
  InstrumentDetail: ({
    ticker,
    signal,
    instrument_type,
    onClose,
  }: {
    ticker: string;
    signal?: { action: string; reason: string; confidence?: number | null } | null;
    instrument_type?: string | null;
    onClose: () => void;
  }) => (
    <div data-testid="detail">
      Detail for {ticker}
      {instrument_type && <div>Type: {instrument_type}</div>}
      {signal && (
        <div>
          {signal.action} - {signal.reason}
          {signal.confidence != null && (
            <div>Confidence: {Math.round(signal.confidence * 100)}%</div>
          )}
        </div>
      )}
      <button onClick={onClose}>x</button>
    </div>
  ),
}));

describe("TopMoversPage", () => {
  it("renders movers and refetches on period change", async () => {
    render(
      <MemoryRouter>
        <TopMoversPage />
      </MemoryRouter>,
    );

    await waitFor(() => expect(mockGetGroupInstruments).toHaveBeenCalledWith("all"));
    await waitFor(() =>
      expect(mockGetOpportunities).toHaveBeenCalledWith({
        group: "all",
        days: 1,
        limit: 10,
        minWeight: 0,
      }),
    );
    expect((await screen.findAllByText("AAA")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("BBB")).length).toBeGreaterThan(0);

    const selects = screen.getAllByRole("combobox");
    const periodSelect = selects[1];
    await userEvent.selectOptions(periodSelect, "1w");
    await waitFor(() => expect(periodSelect).toHaveValue("1w"));
    await waitFor(() =>
      expect(mockGetOpportunities).toHaveBeenLastCalledWith({
        group: "all",
        days: 7,
        limit: 10,
        minWeight: 0,
      }),
    );
  });

  it("fetches watchlist opportunities when selecting FTSE 100", async () => {
    render(
      <MemoryRouter>
        <TopMoversPage />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(mockGetOpportunities).toHaveBeenCalledWith({
        group: "all",
        days: 1,
        limit: 10,
        minWeight: 0,
      }),
    );

    const selects = await screen.findAllByRole("combobox");
    const watchlistSelect = selects[0] as HTMLSelectElement;
    await userEvent.selectOptions(watchlistSelect, "FTSE 100");
    await waitFor(() => expect(watchlistSelect).toHaveValue("FTSE 100"));
    await waitFor(() =>
      expect(mockGetOpportunities).toHaveBeenCalledWith(
        expect.objectContaining({
          tickers: ["AAA", "BBB"],
        }),
      ),
    );
  });

  it("mounts InstrumentDetail with signal when ticker clicked", async () => {
    render(
      <MemoryRouter>
        <TopMoversPage />
      </MemoryRouter>,
    );

    await screen.findByText(/go long/i);

    const button = await screen.findByRole("button", { name: "AAA" });
    fireEvent.click(button);
    const detail = await screen.findByTestId("detail");
    expect(detail).toHaveTextContent("AAA");
    expect(detail).toHaveTextContent(/BUY/i);
    expect(detail).toHaveTextContent("go long");
  });

  it("passes instrument_type through to InstrumentDetail instead of dropping it (#6876)", async () => {
    render(
      <MemoryRouter>
        <TopMoversPage />
      </MemoryRouter>,
    );

    const button = await screen.findByRole("button", { name: "AAA" });
    fireEvent.click(button);
    const detail = await screen.findByTestId("detail");
    expect(detail).toHaveTextContent("Type: stock");
  });

  it("colors gainers green and losers red", async () => {
    render(
      <MemoryRouter>
        <TopMoversPage />
      </MemoryRouter>,
    );

    const gainerCandidates = await screen.findAllByText("5.00");
    const gainerCell = gainerCandidates.find(
      (el) => (el as HTMLElement).style.color === "green",
    ) as HTMLElement;
    const loserCell = await screen.findByText("-2.00");
    expect(gainerCell).toHaveStyle({ color: "rgb(0, 128, 0)" });
    expect(loserCell).toHaveStyle({ color: "rgb(255, 0, 0)" });
  });

  it("renders trading signals beside movers and passes them to detail", async () => {
    render(
      <MemoryRouter>
        <TopMoversPage />
      </MemoryRouter>,
    );
    const tickerBtn = await screen.findByRole("button", { name: "AAA" });
    const row = tickerBtn.closest("tr");
    expect(row).not.toBeNull();
    const badge = within(row as HTMLElement).getByText(/buy/i);
    expect(badge).toHaveAttribute("title", "go long");
    fireEvent.click(badge);
    const detail = await screen.findByTestId("detail");
    expect(detail).toHaveTextContent("AAA");
    expect(detail).toHaveTextContent(/BUY/i);
    expect(detail).toHaveTextContent("go long");
  });

  it("shows HTTP status when fetch fails", async () => {
    mockGetOpportunities.mockImplementationOnce(() => {
      throw new Error("HTTP 401 – Unauthorized");
    });
    render(
      <MemoryRouter>
        <TopMoversPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/HTTP 401/)).toBeInTheDocument();
  });

  it("falls back to FTSE 100 and prompts login on 401", async () => {
    mockGetOpportunities.mockImplementationOnce(() => {
      const err = new Error("HTTP 401 – Unauthorized");
      return Promise.reject(err);
    });
    render(
      <MemoryRouter>
        <TopMoversPage />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(mockGetOpportunities).toHaveBeenCalledWith(
        expect.objectContaining({
          tickers: ["AAA", "BBB"],
        }),
      ),
    );

    const selects = await screen.findAllByRole("combobox");
    const watchlistSelect = selects[0] as HTMLSelectElement;
    await waitFor(() => expect(watchlistSelect.value).toBe("FTSE 100"));

    expect(
      await screen.findByText(/log in to view portfolio-based movers/i),
    ).toBeInTheDocument();
  });

  it("passes min weight when exclude checkbox checked", async () => {
    render(
      <MemoryRouter>
        <TopMoversPage />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(mockGetOpportunities).toHaveBeenCalledWith({
        group: "all",
        days: 1,
        limit: 10,
        minWeight: 0,
      }),
    );

    const checkbox = screen.getByLabelText(/Exclude positions/i);
    fireEvent.click(checkbox);

    await waitFor(() =>
      expect(mockGetOpportunities).toHaveBeenLastCalledWith({
        group: "all",
        days: 1,
        limit: 10,
        minWeight: 0.5,
      }),
    );
  });

  it("reuses the Trading page's exact disclaimer string (trading.description) and labels the time windows (#7231)", async () => {
    render(
      <MemoryRouter>
        <TopMoversPage />
      </MemoryRouter>,
    );

    // Wait for the loaded table (not just the transient loading state) so the
    // assertions below read the settled tree, not the one React replaces a
    // moment later when the fetch resolves.
    await screen.findAllByText("AAA");

    // Assert against the shared translation key's actual value, not a
    // hardcoded copy of the English sentence, so a second, drifted
    // disclaimer variant on Movers would fail this test.
    expect(
      screen.getByText(enTranslation.trading.description),
    ).toBeInTheDocument();
    expect(
      screen.getByText(enTranslation.movers.windowNote),
    ).toBeInTheDocument();
  });

  it("shows page-shaped skeletons instead of a bare loading message while the fetch is pending (#7229)", async () => {
    // getGroupInstruments still resolves normally (fast, default mock); it's
    // the slow /opportunities call that never settles here, which is enough
    // to keep the whole page in its loading state.
    mockGetOpportunities.mockImplementation(() => new Promise(() => {}));

    render(
      <MemoryRouter>
        <TopMoversPage />
      </MemoryRouter>,
    );

    // Controls render immediately, independent of the slow /opportunities call.
    expect(screen.getAllByRole("combobox").length).toBeGreaterThan(0);

    // The old bare "Loading…" paragraph is gone, replaced by qualified,
    // screen-reader-announced skeletons.
    expect(screen.queryByText("Loading…")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
    });
    expect(document.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);

    // Exactly one live region for the whole loading page, not one per
    // skeleton placeholder (regression guard: multiple skeleton instances
    // each carrying the same label produces a screen-reader barrage).
    expect(screen.getAllByRole("status")).toHaveLength(1);

    // A coarser regression guard: the loading gate must not be dropped
    // entirely while a fetch is genuinely pending. This does NOT exercise
    // the pre-effect `loading:false, data:null, error:null` frame that
    // `computeMoversLoading` exists to cover -- RTL's `render` is
    // act()-wrapped, so React has already flushed the effect and `loading`
    // is `true` by the time this assertion runs. See the
    // `computeMoversLoading` unit tests below for the guard that actually
    // pins that frame.
    expect(screen.queryByText("No signals.")).not.toBeInTheDocument();
  });

  it("does not tell mobile users (who have no hover) to hover for signal context (#7231)", () => {
    expect(enTranslation.movers.windowNote.toLowerCase()).not.toContain("hover");
    expect(enTranslation.movers.signalWindowNote.toLowerCase()).not.toContain("hover");
  });

  it("surfaces a signal's reason and confidence without leaving the page when its badge is selected (#7231)", async () => {
    const signalWithConfidence: TradingSignal = {
      ticker: "AAA",
      action: "BUY",
      reason: "go long",
      confidence: 0.82,
    };
    mockGetOpportunities.mockImplementation((opts: { group?: string; tickers?: string[] }) => {
      if (opts.group === "all") {
        return Promise.resolve({
          entries: [
            { ...groupEntries[0], signal: signalWithConfidence },
            groupEntries[1],
          ],
          signals: [signalWithConfidence],
          context: { source: "group", group: "all", days: 1, anomalies: [] },
        });
      }
      return Promise.resolve({
        entries: watchlistEntries,
        signals: [],
        context: { source: "watchlist", tickers: opts.tickers ?? [], days: 1, anomalies: [] },
      });
    });

    render(
      <MemoryRouter>
        <TopMoversPage />
      </MemoryRouter>,
    );

    const tickerBtn = await screen.findByRole("button", { name: "AAA" });
    const row = tickerBtn.closest("tr");
    expect(row).not.toBeNull();

    // The badge is a real, keyboard-reachable button whose accessible name
    // announces both the action and that it can be selected for more detail.
    const badge = within(row as HTMLElement).getByRole("button", {
      name: /buy signal.*select to view reason and confidence/i,
    });
    fireEvent.click(badge);

    const detail = await screen.findByTestId("detail");
    expect(detail).toHaveTextContent("go long");
    expect(detail).toHaveTextContent("Confidence: 82%");
  });

  it("labels the % and Δ column headers with the selected period instead of bare symbols (#7231)", async () => {
    render(
      <MemoryRouter>
        <TopMoversPage />
      </MemoryRouter>,
    );

    await screen.findAllByText("AAA");
    expect(
      screen.getByRole("columnheader", { name: /Price change \(%, 1d\)/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: /Value change \(£, 1d\)/i }),
    ).toBeInTheDocument();

    const selects = screen.getAllByRole("combobox");
    const periodSelect = selects[1];
    await userEvent.selectOptions(periodSelect, "1w");
    await waitFor(() => expect(periodSelect).toHaveValue("1w"));

    expect(
      screen.getByRole("columnheader", { name: /Price change \(%, 1w\)/i }),
    ).toBeInTheDocument();
  });

  it("does not emit duplicate-key warnings when the same ticker appears twice (#6505)", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    mockGetOpportunities.mockResolvedValue({
      entries: [
        { ticker: "CASH", name: "Cash GBP", change_pct: 5, side: "gainers" },
        { ticker: "CASH", name: "Cash L", change_pct: 3, side: "gainers" },
        { ticker: "PFE", name: "Pfizer N", change_pct: -2, side: "losers" },
        { ticker: "PFE", name: "Pfizer L", change_pct: -4, side: "losers" },
      ],
      signals: [],
      context: { source: "group", group: "all", days: 1, anomalies: [] },
    });

    render(
      <MemoryRouter>
        <TopMoversPage />
      </MemoryRouter>,
    );

    await waitFor(() => expect(mockGetOpportunities).toHaveBeenCalled());
    // Both duplicate entries must render before we can trust the warning check.
    expect(await screen.findAllByText("CASH")).toHaveLength(2);
    expect(await screen.findAllByText("PFE")).toHaveLength(2);
    const keyWarnings = errorSpy.mock.calls.filter((args) =>
      String(args[0]).includes("same key"),
    );
    expect(keyWarnings).toEqual([]);
    errorSpy.mockRestore();
  });
});

describe("computeMoversLoading (#7229)", () => {
  // `useFetch` initialises `loading` to `false` and only flips it to `true`
  // inside a `useEffect`, so the very first render commits with
  // `loading:false, data:null, error:null`. This is the exact case a
  // JSX-level test (RTL's act()-wrapped `render`) cannot observe, because by
  // the time an assertion runs the effect has already flushed and `loading`
  // is `true` on its own -- so it's pinned directly against the pure
  // function instead.
  it("treats the pre-effect frame (loading=false, data=null, error=null) as still loading", () => {
    expect(computeMoversLoading(false, null, null)).toBe(true);
  });

  it("is loading whenever `loading` is true, regardless of data/error", () => {
    expect(computeMoversLoading(true, null, null)).toBe(true);
    expect(computeMoversLoading(true, { entries: [], signals: [] }, null)).toBe(true);
  });

  it("is not loading once data has resolved", () => {
    expect(computeMoversLoading(false, { entries: [], signals: [] }, null)).toBe(false);
  });

  it("is not loading once an error is present, even with no data yet", () => {
    expect(computeMoversLoading(false, null, new Error("boom"))).toBe(false);
  });
});
