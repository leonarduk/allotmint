import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { act } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/api", () => ({
  getQuotes: vi.fn(),
}));

import { Watchlist } from "@/pages/Watchlist";
import { getQuotes } from "@/api";
import type { QuoteRow } from "@/types";

// Watchlist rows link to /research/:symbol (#7218), so every render needs
// a Router in scope.
function renderWatchlist() {
  return render(
    <MemoryRouter>
      <Watchlist />
    </MemoryRouter>,
  );
}

const sampleRows: QuoteRow[] = [
  {
    name: "Alpha",
    symbol: "AAA",
    last: 10,
    open: 9,
    high: 11,
    low: 8,
    change: 1,
    changePct: 10,
    volume: 1000,
    marketTime: "2024-01-01T00:00:00Z",
    marketState: "REGULAR",
  },
  {
    name: "Beta",
    symbol: "BBB",
    last: 5,
    open: 6,
    high: 6,
    low: 4,
    change: -1,
    changePct: -20,
    volume: 2000,
    marketTime: "2024-01-01T01:00:00Z",
    marketState: "REGULAR",
  },
];

async function flushPromises() {
  await Promise.resolve();
  await Promise.resolve();
  await vi.advanceTimersByTimeAsync(0);
}

// The symbol also appears in the "Watched tickers" chip list above the
// table, so a plain findByText("SYMBOL") is ambiguous. Table rows (and only
// table rows) have an implicit "row" accessible role, so search there.
async function findRow(symbol: string) {
  // findAllByRole resolves as soon as the (always-present) header row
  // exists, not once the fetched data has rendered -- wait until a matching
  // data row actually shows up.
  return waitFor(() => {
    const rows = screen.getAllByRole("row");
    const row = rows.find((r) => r.textContent?.includes(symbol));
    if (!row) throw new Error(`No table row found for ${symbol}`);
    return row;
  });
}

describe("Watchlist page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("renders quotes and sorts columns", async () => {
    (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue(sampleRows);
    localStorage.setItem("watchlistSymbols", "AAA,BBB");

    renderWatchlist();

    expect(await screen.findByText("Alpha")).toBeInTheDocument();
    expect(getQuotes).toHaveBeenCalledWith(["AAA", "BBB"]);

    let rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("AAA");
    expect(rows[1]).toHaveTextContent("BBB");

    fireEvent.click(screen.getByText("Chg %"));
    rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("BBB");

    fireEvent.click(screen.getByText("Chg %"));
    rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("AAA");
  });

  it("shows error message when API fails", async () => {
    (getQuotes as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("boom"));
    localStorage.setItem("watchlistSymbols", "AAA");

    const { unmount } = renderWatchlist();

    expect(await screen.findByText("boom")).toBeInTheDocument();

    unmount();
  });

  it("allows manual refresh and auto-refresh", async () => {
    vi.useFakeTimers();
    (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue([sampleRows[0]]);
    localStorage.setItem("watchlistSymbols", "AAA");
    const { unmount } = renderWatchlist();

    await flushPromises();
    expect(screen.getAllByText("Alpha")[0]).toBeInTheDocument();
    expect(getQuotes).toHaveBeenCalledTimes(1);

    fireEvent.click(
      screen.getAllByRole("button", { name: /refresh/i })[0],
    );
    await act(async () => Promise.resolve());

    expect(getQuotes).toHaveBeenCalledTimes(2);

    await vi.advanceTimersByTimeAsync(10000);
    await flushPromises();
    expect(getQuotes).toHaveBeenCalledTimes(3);

    unmount();
    vi.useRealTimers();
  });

  it("auto-refreshes when enabled", async () => {
    vi.useFakeTimers();
    (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue([sampleRows[0]]);
    localStorage.setItem("watchlistSymbols", "AAA");

    const { unmount } = renderWatchlist();

    await flushPromises();
    expect(screen.getAllByText("Alpha")[0]).toBeInTheDocument();
    expect(getQuotes).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(10000);
    await flushPromises();
    expect(getQuotes).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
    unmount();
  });

  it("allows toggling refresh frequency", async () => {
    vi.useFakeTimers();
    (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue([sampleRows[0]]);
    localStorage.setItem("watchlistSymbols", "AAA");

    const { unmount } = renderWatchlist();

    await flushPromises();
    expect(screen.getAllByText("Alpha")[0]).toBeInTheDocument();

    expect(getQuotes).toHaveBeenCalledTimes(1);

    fireEvent.change(screen.getAllByLabelText(/Auto-refresh/)[0], {
      target: { value: "0" },
    });

    await vi.advanceTimersByTimeAsync(10000);
    await flushPromises();
    expect(getQuotes).toHaveBeenCalledTimes(1);

    fireEvent.change(screen.getAllByLabelText(/Auto-refresh/)[0], {
      target: { value: "60000" },
    });

    await vi.advanceTimersByTimeAsync(10000);
    await flushPromises();
    expect(getQuotes).toHaveBeenCalledTimes(2);

    unmount();
    vi.useRealTimers();
  });

  it("skips auto-refresh when markets are closed", async () => {
    vi.useFakeTimers();
    const closed = [{ ...sampleRows[0], marketState: "CLOSED" }];
    (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue(closed);
    localStorage.setItem("watchlistSymbols", "AAA");

    const { unmount } = renderWatchlist();

    await flushPromises();
    expect(screen.getAllByText("Alpha")[0]).toBeInTheDocument();
    expect(getQuotes).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(10000);
    await flushPromises();
    expect(screen.getAllByText(/markets/i)[0]).toBeInTheDocument();
    expect(getQuotes).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(30000);
    await flushPromises();
    expect(getQuotes).toHaveBeenCalledTimes(1);

    unmount();
    vi.useRealTimers();
  });

  describe("symbol chip editor (#7110)", () => {
    beforeEach(() => {
      (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue([]);
      localStorage.setItem("watchlistSymbols", "AAA,BBB");
    });

    it("gives the add field an accessible name and renders a chip per symbol", async () => {
      renderWatchlist();

      expect(
        await screen.findByLabelText("Watched tickers"),
      ).toBeInTheDocument();
      expect(screen.getByLabelText("Remove AAA")).toBeInTheDocument();
      expect(screen.getByLabelText("Remove BBB")).toBeInTheDocument();
    });

    it("adds a typed ticker on Enter, uppercased, and clears the field", async () => {
      renderWatchlist();

      const input = (await screen.findByLabelText(
        "Watched tickers",
      )) as HTMLInputElement;
      fireEvent.change(input, { target: { value: " ccc " } });
      fireEvent.keyDown(input, { key: "Enter" });

      expect(input.value).toBe("");
      expect(screen.getByLabelText("Remove CCC")).toBeInTheDocument();
      expect(localStorage.getItem("watchlistSymbols")).toBe("AAA,BBB,CCC");
    });

    it("removes a symbol via its chip button", async () => {
      renderWatchlist();

      fireEvent.click(await screen.findByLabelText("Remove AAA"));

      expect(screen.queryByLabelText("Remove AAA")).not.toBeInTheDocument();
      expect(localStorage.getItem("watchlistSymbols")).toBe("BBB");
    });

    it("ignores a duplicate regardless of case", async () => {
      renderWatchlist();

      const input = (await screen.findByLabelText(
        "Watched tickers",
      )) as HTMLInputElement;
      fireEvent.change(input, { target: { value: "aaa" } });
      fireEvent.click(screen.getByRole("button", { name: "Add" }));

      expect(input.value).toBe("");
      expect(localStorage.getItem("watchlistSymbols")).toBe("AAA,BBB");
    });

    it("splits a pasted comma-separated list instead of storing it as one symbol", async () => {
      renderWatchlist();

      const input = (await screen.findByLabelText(
        "Watched tickers",
      )) as HTMLInputElement;
      fireEvent.change(input, { target: { value: "CCC, DDD ,AAA" } });
      fireEvent.keyDown(input, { key: "Enter" });

      expect(localStorage.getItem("watchlistSymbols")).toBe("AAA,BBB,CCC,DDD");
      expect(screen.getByLabelText("Remove CCC")).toBeInTheDocument();
      expect(screen.getByLabelText("Remove DDD")).toBeInTheDocument();
    });
  });

  describe("table formatting (#7218)", () => {
    it("links a known-instrument row to /research/:symbol, not /instrument/:symbol", async () => {
      // Caught in review: /instrument/:group is the catalogue editor
      // filtered by group slug, not the research page -- linking there sent
      // "VUSA.L" in as an unknown group. Assert the actual href, not just
      // that *a* link exists, since that weaker assertion is exactly what
      // let the wrong route ship originally.
      (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue([sampleRows[0]]);
      localStorage.setItem("watchlistSymbols", "AAA");

      renderWatchlist();

      const row = await findRow("AAA");
      const links = row.querySelectorAll("a");
      expect(links.length).toBeGreaterThan(0);
      links.forEach((a) => {
        expect(a.getAttribute("href")).toBe("/research/AAA");
      });
    });

    it("does not link an index/FX row that has no research page", async () => {
      const fxRow: QuoteRow = {
        ...sampleRows[0],
        name: "EUR/GBP",
        symbol: "EURGBP=X",
      };
      (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue([fxRow]);
      localStorage.setItem("watchlistSymbols", "EURGBP=X");

      renderWatchlist();

      const row = await findRow("EURGBP=X");
      expect(row.querySelectorAll("a").length).toBe(0);
    });

    it("keeps toFixed precision sign-independent for crypto Chg (regression)", async () => {
      // pricePrecision's sub-$1 crypto clause used to be evaluated against
      // whatever value was currently being formatted. Fed the *change*
      // value, every negative change is "< 1", so a real BTC-USD move of
      // -124 (last 78404, well over $1) rendered as "-124.00000" (5dp)
      // while the same-sized "+124" rendered "+124.00" (2dp). Precision must
      // depend on the instrument's price level (Last), not the change's own
      // sign or magnitude.
      const btcRow: QuoteRow = {
        name: "Bitcoin USD",
        symbol: "BTC-USD",
        last: 78404,
        open: 78528,
        high: 78600,
        low: 78300,
        change: -124,
        changePct: -0.16,
        volume: 30282878976,
        marketTime: "2024-01-01T00:00:00Z",
        marketState: "REGULAR",
      };
      (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue([btcRow]);
      localStorage.setItem("watchlistSymbols", "BTC-USD");

      renderWatchlist();

      const row = await findRow("BTC-USD");
      expect(row).toHaveTextContent("-124.00");
      expect(row).not.toHaveTextContent("-124.00000");
    });

    it("still uses 5dp for a genuinely sub-$1 crypto's negative change", async () => {
      const dogeRow: QuoteRow = {
        name: "Dogecoin USD",
        symbol: "DOGE-USD",
        last: 0.15234,
        open: 0.15789,
        high: 0.15900,
        low: 0.15100,
        change: -0.00555,
        changePct: -3.6,
        volume: 12345678,
        marketTime: "2024-01-01T00:00:00Z",
        marketState: "REGULAR",
      };
      (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue([dogeRow]);
      localStorage.setItem("watchlistSymbols", "DOGE-USD");

      renderWatchlist();

      const row = await findRow("DOGE-USD");
      expect(row).toHaveTextContent("-0.00555");
    });

    it("prefers a currency reported by the quote payload over the symbol-suffix guess", async () => {
      const row: QuoteRow = {
        ...sampleRows[0],
        symbol: "IWDA.AS",
        currency: "GBP", // deliberately not what the .AS fallback would guess
      };
      (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue([row]);
      localStorage.setItem("watchlistSymbols", "IWDA.AS");

      renderWatchlist();

      const tr = await findRow("IWDA.AS");
      expect(tr.querySelectorAll("td")[2]).toHaveTextContent("GBP");
    });

    it("shows — rather than guessing when neither a currency nor a recognised suffix is available", async () => {
      const row: QuoteRow = {
        ...sampleRows[0],
        symbol: "7203.T", // Tokyo-listed; not in the suffix fallback table
        currency: null,
      };
      (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue([row]);
      localStorage.setItem("watchlistSymbols", "7203.T");

      renderWatchlist();

      const tr = await findRow("7203.T");
      expect(tr.querySelectorAll("td")[2]).toHaveTextContent("—");
    });

    it("shows a non-zero EURGBP=X Chg consistent with Chg %, matching Last's precision", async () => {
      // Reproduces the bug exactly: formatValue already rendered Last to 5
      // decimal places for =X symbols, but formatChange was hardcoded to
      // toFixed(2), so a real 0.0018 move rounded away to "+0.00" while
      // Chg % correctly showed "+0.21%". Both formatters now derive their
      // precision from the same pricePrecision(symbol, val) helper.
      const fxRow: QuoteRow = {
        name: "EUR/GBP",
        symbol: "EURGBP=X",
        last: 0.85721,
        open: 0.85541,
        high: 0.85801,
        low: 0.85501,
        change: 0.0018,
        changePct: 0.21,
        volume: 0,
        marketTime: "2024-01-01T00:00:00Z",
        marketState: "REGULAR",
      };
      (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue([fxRow]);
      localStorage.setItem("watchlistSymbols", "EURGBP=X");

      renderWatchlist();

      const row = await findRow("EURGBP=X");
      expect(row).toHaveTextContent("0.85721"); // Last, 5dp
      expect(row).toHaveTextContent("+0.00180"); // Chg, same 5dp -- not "+0.00"
      expect(row).toHaveTextContent("+0.21%"); // Chg % (unaffected, already correct)
    });

    it("renders — for volume on index/FX rows but a genuine 0 for an equity row", async () => {
      // The feed sends literal 0 (not null) for index/FX volume because
      // those symbol types never have a traded volume at all -- rendering
      // "0" reads as "nothing traded today", which is false, so it's masked
      // to "—". An equity/ETF genuinely reporting 0 volume (e.g. a very
      // thinly traded row with no prints yet today) is left as "0": there is
      // no field in the feed that distinguishes "not applicable" from "no
      // trades so far" for that symbol type, so masking it would hide real
      // (if unusual) information. This is a deliberate judgment call, not a
      // limitation we could resolve with more data from this payload.
      const indexRow: QuoteRow = {
        name: "FTSE 100",
        symbol: "^FTSE",
        last: 10878,
        open: 10870,
        high: 10890,
        low: 10860,
        change: -8.04,
        changePct: -0.07,
        volume: 0,
        marketTime: "2024-01-01T00:00:00Z",
        marketState: "REGULAR",
      };
      const equityRow: QuoteRow = {
        name: "Thinly Traded Co",
        symbol: "TTC.L",
        last: 100,
        open: 100,
        high: 100,
        low: 100,
        change: 0,
        changePct: 0,
        volume: 0,
        marketTime: "2024-01-01T00:00:00Z",
        marketState: "REGULAR",
      };
      (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue([indexRow, equityRow]);
      localStorage.setItem("watchlistSymbols", "^FTSE,TTC.L");

      renderWatchlist();

      const indexRowEl = await findRow("^FTSE");
      const equityRowEl = await findRow("TTC.L");
      // "—" appears elsewhere too (e.g. no data yet), so scope to the Vol cell.
      expect(indexRowEl.querySelectorAll("td")[9]).toHaveTextContent("—");
      expect(equityRowEl.querySelectorAll("td")[9]).toHaveTextContent("0");
    });

    it("labels the unit for each symbol type: index, crypto (USD), EUR, GBp and an FX rate", async () => {
      const rows: QuoteRow[] = [
        {
          name: "FTSE 100",
          symbol: "^FTSE",
          last: 10878,
          open: null,
          high: null,
          low: null,
          change: -8.04,
          changePct: -0.07,
          volume: 0,
          marketTime: null,
          marketState: "REGULAR",
        },
        {
          name: "Bitcoin USD",
          symbol: "BTC-USD",
          last: 78404,
          open: null,
          high: null,
          low: null,
          change: -124,
          changePct: -0.16,
          volume: 30282878976,
          marketTime: null,
          marketState: "REGULAR",
        },
        {
          name: "iShares Core MSCI World",
          symbol: "IWDA.AS",
          last: 126.67,
          open: null,
          high: null,
          low: null,
          change: 0.14,
          changePct: 0.11,
          volume: 65442,
          marketTime: null,
          marketState: "REGULAR",
        },
        {
          name: "Vanguard S&P 500",
          symbol: "VUSA.L",
          last: 107.02,
          open: null,
          high: null,
          low: null,
          change: 0.36,
          changePct: 0.34,
          volume: 211086,
          marketTime: null,
          marketState: "REGULAR",
        },
        {
          name: "USD/GBP",
          symbol: "USDGBP=X",
          last: 0.73559,
          open: null,
          high: null,
          low: null,
          change: 0.003,
          changePct: 0.41,
          volume: 0,
          marketTime: null,
          marketState: "REGULAR",
        },
      ];
      (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue(rows);
      localStorage.setItem(
        "watchlistSymbols",
        "^FTSE,BTC-USD,IWDA.AS,VUSA.L,USDGBP=X",
      );

      renderWatchlist();

      const unitCell = async (symbol: string) => {
        const row = await findRow(symbol);
        return row.querySelectorAll("td")[2]; // Unit column
      };

      expect(await unitCell("^FTSE")).toHaveTextContent("pts");
      expect(await unitCell("BTC-USD")).toHaveTextContent("USD");
      expect(await unitCell("IWDA.AS")).toHaveTextContent("EUR");
      expect(await unitCell("VUSA.L")).toHaveTextContent("GBp");
      // USDGBP=X's unit is rendered as the pair itself (USD/GBP) rather than
      // a bare "GBP", since a bare currency code wouldn't say which pair the
      // rate belongs to -- this is the "FX rate" / "GBP-denominated" case
      // from #7218 called out together.
      expect(await unitCell("USDGBP=X")).toHaveTextContent("USD/GBP");
    });
  });

  describe("currency/unit labelling and full names (#7232)", () => {
    it("marks an index level as points rather than a currency, even when the feed also sends one", async () => {
      // quoteType "INDEX" takes priority over a reported currency: an index
      // level is a points figure, not a currency amount, even when the feed
      // sends a currency code (e.g. "GBP") alongside it.
      const rows: QuoteRow[] = [
        {
          name: "FTSE 100",
          symbol: "^FTSE",
          last: 10878,
          open: null,
          high: null,
          low: null,
          change: -8.04,
          changePct: -0.07,
          volume: null,
          marketTime: null,
          marketState: "REGULAR",
          currency: "GBP",
          quoteType: "INDEX",
        },
      ];
      (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue(rows);
      localStorage.setItem("watchlistSymbols", "^FTSE");

      renderWatchlist();

      const row = await findRow("^FTSE");
      expect(row).toHaveTextContent("pts");
      expect(row).not.toHaveTextContent("GBP");
    });

    it("keeps a pence-quoted row's GBX label and its unscaled magnitude (#7219)", async () => {
      // The backend canonicalises yfinance's exact-case "GBp" pence token
      // to the visually distinct "GBX" before this ever reaches the
      // frontend (backend/routes/quotes.py), so QuoteRow.currency here is
      // already "GBX" -- but nothing in the frontend must scale the price
      // by 100 to "convert" it. BP.L trades around 517p, not GBP 5.17.
      const rows: QuoteRow[] = [
        {
          name: "BP p.l.c.",
          symbol: "BP.L",
          last: 517.05,
          open: null,
          high: null,
          low: null,
          change: 2.5,
          changePct: 0.49,
          volume: null,
          marketTime: null,
          marketState: "REGULAR",
          currency: "GBX",
          quoteType: "EQUITY",
        },
      ];
      (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue(rows);
      localStorage.setItem("watchlistSymbols", "BP.L");

      renderWatchlist();

      const row = await findRow("BP.L");
      expect(row).toHaveTextContent("517.05");
      expect(row).toHaveTextContent("GBX");
      expect(row).not.toHaveTextContent("5.17");
      expect(row).not.toHaveTextContent("GBP");
    });

    it("renders the untruncated name the API now sends and doesn't clip it with CSS", async () => {
      // Yahoo hard-truncates yfinance's `shortName` at 31 characters --
      // the un-truncated `longName` for this instrument is "Vanguard S&P
      // 500 UCITS ETF" and, per #7232 MUST FIX 1, the backend now prefers
      // longName. This fixture is that real API value, not a hand-written
      // stand-in, so this test only proves the frontend correctly renders
      // and doesn't re-truncate whatever full name it is given.
      const fullName = "Vanguard S&P 500 UCITS ETF";
      const rows: QuoteRow[] = [
        {
          name: fullName,
          symbol: "VUSA.L",
          last: 107.02,
          open: null,
          high: null,
          low: null,
          change: 0.36,
          changePct: 0.34,
          volume: null,
          marketTime: null,
          marketState: "REGULAR",
          currency: "GBX",
          quoteType: "ETF",
        },
      ];
      (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue(rows);
      localStorage.setItem("watchlistSymbols", "VUSA.L");

      renderWatchlist();

      const nameCell = await screen.findByText(fullName);
      expect(nameCell).toBeInTheDocument();
      expect(nameCell).toHaveAttribute("title", fullName);
      // Regression guard for the CSS fix itself: reverting to
      // `white-space: nowrap; text-overflow: ellipsis` would leave the
      // full name in the DOM (jsdom doesn't lay out text, so a plain
      // text-content assertion can't catch that revert) but would flip
      // these inline style properties back.
      expect(nameCell.style.whiteSpace).not.toBe("nowrap");
      expect(nameCell.style.textOverflow).not.toBe("ellipsis");
    });
  });
});
