import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { TopMoversPage } from "@/components/TopMoversPage";
import type { OpportunityEntry, TradingSignal } from "@/types";

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
    onClose,
  }: {
    ticker: string;
    signal?: { action: string; reason: string } | null;
    onClose: () => void;
  }) => (
    <div data-testid="detail">
      Detail for {ticker}
      {signal && (
        <div>
          {signal.action} - {signal.reason}
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
});
