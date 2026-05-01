import { render, screen, waitFor, act, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { GroupPortfolioView } from "@/components/GroupPortfolioView";
import i18n from "@/i18n";
import { configContext, type AppConfig } from "@/ConfigContext";
import { useState } from "react";
import * as api from "@/api";
import { MemoryRouter } from "react-router-dom";
import type { OwnerSummary } from "@/types";
vi.mock("@/components/TopMoversSummary", () => ({
  TopMoversSummary: () => <div data-testid="top-movers-summary" />,
}));

beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  api.clearGroupInstrumentCache();
  vi
    .spyOn(api, "getCachedGroupInstruments")
    .mockImplementation((slug, filters) => api.getGroupInstruments(slug, filters));
});

afterEach(async () => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  api.clearGroupInstrumentCache();
  await act(async () => {
    await i18n.changeLanguage("en");
  });
});

const defaultConfig: AppConfig = {
  relativeViewEnabled: false,
  theme: "system",
  baseCurrency: "GBP",
  tabs: {
    group: true,
    market: true,
    owner: true,
    instrument: true,
    performance: true,
    transactions: true,
    trading: true,
    screener: true,
    timeseries: true,
    watchlist: true,
    allocation: true,
    rebalance: true,
    movers: true,
    instrumentadmin: true,
    dataadmin: true,
    virtual: true,
    support: true,
    settings: true,
    pension: true,
    reports: true,
    scenario: true,
  },
};

const TestProvider = ({ children }: { children: React.ReactNode }) => {
  const [relativeViewEnabled, setRelativeViewEnabled] = useState(false);
  return (
    <configContext.Provider
      value={{
        ...defaultConfig,
        relativeViewEnabled,
        setRelativeViewEnabled,
        refreshConfig: async () => {},
        setBaseCurrency: () => {},
      }}
    >
      {children}
    </configContext.Provider>
  );
};

const renderWithConfig = (ui: React.ReactElement) =>
  render(
    <MemoryRouter>
      <TestProvider>{ui}</TestProvider>
    </MemoryRouter>
  );

const instrumentKey = (owner?: string | null, account?: string | null) =>
  `${owner ?? ""}::${account ?? ""}`;

const ownerFixtures: OwnerSummary[] = [
  { owner: "alice", full_name: "Alice Example", accounts: ["isa", "sipp"] },
  { owner: "bob", full_name: "Bob Example", accounts: ["isa"] },
];

const toUrlString = (input: RequestInfo | URL) => {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  if (typeof input === "object" && input && "url" in input) {
    return (input as Request).url;
  }
  return String(input);
};

const mockAllFetches = (
  portfolio: any,
  options: {
    metrics?: { alpha?: any; trackingError?: any; maxDrawdown?: any };
    instruments?: Record<string, any[]>;
  } = {},
) => {
  const { metrics, instruments = {} } = options;
  const { alpha = 0, trackingError = 0, maxDrawdown = 0 } = metrics ?? {};
  const defaultInstrumentRows =
    instruments[instrumentKey(undefined, undefined)] ?? [];
  const normalizedPortfolio = {
    slug: portfolio.slug ?? "all",
    name: portfolio.name ?? "At a glance",
    as_of: portfolio.as_of ?? "2024-01-01T00:00:00Z",
    members: portfolio.members ?? [],
    total_value_estimate_gbp:
      portfolio.total_value_estimate_gbp ??
      (Array.isArray(portfolio.accounts)
        ? portfolio.accounts.reduce(
            (sum: number, account: any) => sum + Number(account.value_estimate_gbp ?? 0),
            0,
          )
        : 0),
    trades_this_month: portfolio.trades_this_month ?? 0,
    trades_remaining: portfolio.trades_remaining ?? 0,
    accounts: (portfolio.accounts ?? []).map((account: any, _accountIndex: number) => ({
      currency: account.currency ?? "GBP",
      ...account,
      holdings: (account.holdings ?? []).map((holding: any, holdingIndex: number) => ({
        ticker: holding.ticker ?? `${account.owner ?? "owner"}-${account.account_type ?? "acct"}-${holdingIndex}`,
        name: holding.name ?? `Holding ${holdingIndex + 1}`,
        ...holding,
      })),
    })),
  };

  const toUrlString = (input: RequestInfo | URL) => {
    if (typeof input === "string") return input;
    if (input instanceof URL) return input.toString();
    if (typeof input === "object" && input && "url" in input) {
      return (input as Request).url;
    }
    return String(input);
  };

  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = toUrlString(input);
    if (url.includes("/portfolio-group/") && url.includes("/instruments")) {
      const parsed = new URL(url);
      const owner = parsed.searchParams.get("owner");
      const account = parsed.searchParams.get("account_type");
      const key = instrumentKey(owner, account);
      const rows = instruments[key] ?? defaultInstrumentRows;
      return Promise.resolve({
        ok: true,
        json: async () => rows,
      } as Response);
    }
    if (url.includes("/instrument/admin/groups")) {
      return Promise.resolve({
        ok: true,
        json: async () => [],
      } as Response);
    }
    if (url.includes("/instrument/admin/groupings")) {
      return Promise.resolve({
        ok: true,
        json: async () => [],
      } as Response);
    }
    if (url.includes("/portfolio-group/") && url.includes("/movers")) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ gainers: [], losers: [] }),
      } as Response);
    }
    if (url.includes("/trading-agent/signals")) {
      return Promise.resolve({
        ok: true,
        json: async () => [
          { ticker: "AAA", name: "AAA", action: "buy", reason: "" },
        ],
      } as Response);
    }
    if (url.includes("/alpha")) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ alpha_vs_benchmark: alpha }),
      } as Response);
    }
    if (url.includes("tracking-error")) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ tracking_error: trackingError }),
      } as Response);
    }
    if (url.includes("max-drawdown")) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ max_drawdown: maxDrawdown }),
      } as Response);
    }
    if (url.includes("sector-contributions")) {
      return Promise.resolve({
        ok: true,
        json: async () => [],
      } as Response);
    }
    if (url.includes("region-contributions")) {
      return Promise.resolve({
        ok: true,
        json: async () => [],
      } as Response);
    }
    return Promise.resolve({
      ok: true,
      json: async () => normalizedPortfolio,
    } as Response);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
};

describe("GroupPortfolioView", () => {
  it("shows per-owner totals with percentages in relative view", async () => {
    const mockPortfolio = {
      name: "At a glance",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 100,
          holdings: [
            {
              units: 1,
              cost_basis_gbp: 80,
              market_value_gbp: 100,
              day_change_gbp: 5,
            },
          ],
        },
        {
          owner: "bob",
          account_type: "isa",
          value_estimate_gbp: 200,
          holdings: [
            {
              units: 1,
              cost_basis_gbp: 150,
              market_value_gbp: 200,
              day_change_gbp: -10,
            },
          ],
        },
      ],
    };

    mockAllFetches(mockPortfolio);

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    await waitFor(() =>
      expect(screen.getAllByText("Alice Example").length).toBeGreaterThan(0),
    );

    const toggle = screen.getAllByLabelText('Relative view')[0];
    await userEvent.click(toggle);

    const ownerTable = screen
      .getAllByRole("table")
      .find((table) => within(table).queryByText("Owner"));
    expect(ownerTable).toBeTruthy();
    expect(within(ownerTable!).getByText("Alice Example")).toBeInTheDocument();
    expect(within(ownerTable!).getByText("Bob Example")).toBeInTheDocument();
    expect(within(ownerTable!).getAllByText("66.67%").length).toBeGreaterThan(0);
    expect(within(ownerTable!).getByText("25.00%")).toBeInTheDocument();
    expect(within(ownerTable!).getByText("-4.76%")).toBeInTheDocument();
    expect(screen.queryByText("Total Value")).toBeNull();
  });

  it("renders the pricing as-of date", async () => {
    const mockPortfolio = {
      name: "At a glance",
      as_of: "2024-04-01T12:00:00Z",
      accounts: [],
    };

    mockAllFetches(mockPortfolio);

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    await waitFor(() => {
      expect(
        screen.getByText("Pricing as of 2024-04-01", { exact: false }),
      ).toBeInTheDocument();
    });
  });

  it("suppresses day change percentage when the baseline is nearly zero", async () => {
    const mockPortfolio = {
      name: "Tiny balances",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 0.0095,
          holdings: [
            {
              units: 1,
              cost_basis_gbp: 0.0095,
              market_value_gbp: 0.0095,
              day_change_gbp: 0.009,
              instrument_type: "equity",
            },
          ],
        },
      ],
    };

    mockAllFetches(mockPortfolio);

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    await waitFor(() =>
      expect(screen.getAllByText("Alice Example").length).toBeGreaterThan(0),
    );

    const ownerTable = screen
      .getAllByRole("table")
      .find((table) => within(table).queryByText("Owner"));
    expect(ownerTable).toBeTruthy();

    const ownerRow = within(ownerTable!)
      .getAllByRole("row")
      .find((row) => within(row).queryByText("Alice Example"));
    expect(ownerRow).toBeTruthy();

    const ownerCells = within(ownerRow!)
      .getAllByRole("cell")
      .map((cell) => cell.textContent?.trim());
    expect(ownerCells[5]).toBe("—");

    await userEvent.click(ownerRow!);

    await waitFor(() =>
      expect(
        within(ownerTable!)
          .getAllByRole("row")
          .some((row) => within(row).queryByText(/isa/i)),
      ).toBe(true),
    );

    const accountRow = within(ownerTable!)
      .getAllByRole("row")
      .find((row) => within(row).queryByText(/isa/i));
    expect(accountRow).toBeTruthy();

    const accountCells = within(accountRow!)
      .getAllByRole("cell")
      .map((cell) => cell.textContent?.trim());
    expect(accountCells[5]).toBe("—");
  });

  it("renders instrument type pie chart", async () => {
    const mockPortfolio = {
      name: "At a glance",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 100,
          holdings: [
            {
              units: 1,
              cost_basis_gbp: 80,
              market_value_gbp: 100,
              instrument_type: "equity",
            },
          ],
        },
        {
          owner: "bob",
          account_type: "isa",
          value_estimate_gbp: 200,
          holdings: [
            {
              units: 1,
              cost_basis_gbp: 200,
              market_value_gbp: 200,
              instrument_type: "cash",
            },
          ],
        },
      ],
    };

    mockAllFetches(mockPortfolio);

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    await waitFor(() => {
      const containers = document.querySelectorAll(
        ".recharts-responsive-container",
      );
      expect(containers.length).toBeGreaterThan(0);
    });
  });

  it("switches instrument rows across owner and account tabs", async () => {
    const mockPortfolio = {
      name: "At a glance",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 100,
          holdings: [],
        },
        {
          owner: "alice",
          account_type: "general",
          value_estimate_gbp: 50,
          holdings: [],
        },
        {
          owner: "bob",
          account_type: "isa",
          value_estimate_gbp: 200,
          holdings: [],
        },
      ],
    };

    const instruments = {
      [instrumentKey()]: [
        {
          ticker: "ALL",
          name: "All Combined",
          units: 1,
          market_value_gbp: 100,
          gain_gbp: 10,
        },
      ],
      [instrumentKey("alice")]: [
        {
          ticker: "AL-ALL",
          name: "Alice Aggregate",
          units: 2,
          market_value_gbp: 150,
          gain_gbp: 15,
        },
      ],
      [instrumentKey("alice", "isa")]: [
        {
          ticker: "AL-ISA",
          name: "Alice ISA",
          units: 3,
          market_value_gbp: 120,
          gain_gbp: 12,
        },
      ],
      [instrumentKey("bob")]: [
        {
          ticker: "BOB",
          name: "Bob Aggregate",
          units: 4,
          market_value_gbp: 180,
          gain_gbp: 18,
        },
      ],
    };

    const fetchMock = mockAllFetches(mockPortfolio, { instruments });

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([input]) =>
          toUrlString(input as RequestInfo | URL).endsWith("/instruments"),
        ),
      ).toBe(true),
    );
    expect(screen.queryByRole("tab", { name: "All accounts" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "Alice Example" }));

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([input]) =>
          toUrlString(input as RequestInfo | URL).includes("owner=alice"),
        ),
      ).toBe(true),
    );
    const allAccountsTab = screen.getByRole("tab", { name: "All accounts" });
    expect(allAccountsTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "isa" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "isa" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([input]) =>
          toUrlString(input as RequestInfo | URL).includes("owner=alice") &&
          toUrlString(input as RequestInfo | URL).includes("account_type=isa"),
        ),
      ).toBe(true),
    );
    expect(screen.getByRole("tab", { name: "isa" })).toHaveAttribute("aria-selected", "true");

    await userEvent.click(screen.getByRole("tab", { name: "Bob Example" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([input]) =>
          toUrlString(input as RequestInfo | URL).includes("owner=bob"),
        ),
      ).toBe(true),
    );
  });

  it("shows concentration warning when holdings data exceeds 20%", async () => {
    const mockPortfolio = {
      name: "At a glance",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 300,
          holdings: [
            { ticker: "AAA", units: 1, market_value_gbp: 210, instrument_type: "equity" },
            { ticker: "BBB", units: 1, market_value_gbp: 90, instrument_type: "equity" },
          ],
        },
      ],
    };

    mockAllFetches(mockPortfolio, {
      instruments: {
        [instrumentKey()]: [
          { ticker: "AAA", name: "Alpha", market_value_gbp: 60, gain_gbp: 0 },
          { ticker: "BBB", name: "Beta", market_value_gbp: 60, gain_gbp: 0 },
          { ticker: "CCC", name: "Gamma", market_value_gbp: 60, gain_gbp: 0 },
          { ticker: "DDD", name: "Delta", market_value_gbp: 60, gain_gbp: 0 },
          { ticker: "EEE", name: "Epsilon", market_value_gbp: 60, gain_gbp: 0 },
        ],
      },
    });

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    expect(
      await screen.findByText("Top holding AAA is 70.00% of your portfolio"),
    ).toBeInTheDocument();
  });

  it("does not show concentration warning when no holding exceeds 20%", async () => {
    const mockPortfolio = {
      name: "At a glance",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 400,
          holdings: [
            { ticker: "AAA", units: 1, market_value_gbp: 80, instrument_type: "equity" },
            { ticker: "BBB", units: 1, market_value_gbp: 80, instrument_type: "equity" },
            { ticker: "CCC", units: 1, market_value_gbp: 80, instrument_type: "equity" },
            { ticker: "DDD", units: 1, market_value_gbp: 80, instrument_type: "equity" },
            { ticker: "EEE", units: 1, market_value_gbp: 80, instrument_type: "equity" },
          ],
        },
      ],
    };

    mockAllFetches(mockPortfolio);

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    await screen.findByText("At a glance");
    await waitFor(() =>
      expect(screen.queryByText(/Top holding .* is .* of your portfolio/i)).toBeNull(),
    );
  });

  it("does not show concentration warning when filtered to a single owner", async () => {
    const mockPortfolio = {
      name: "At a glance",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 300,
          holdings: [
            { ticker: "AAA", units: 1, market_value_gbp: 210, instrument_type: "equity" },
            { ticker: "BBB", units: 1, market_value_gbp: 90, instrument_type: "equity" },
          ],
        },
        {
          owner: "bob",
          account_type: "isa",
          value_estimate_gbp: 100,
          holdings: [
            { ticker: "CCC", units: 1, market_value_gbp: 100, instrument_type: "equity" },
          ],
        },
      ],
    };

    mockAllFetches(mockPortfolio, {
      instruments: {
        [instrumentKey("alice")]: [
          { ticker: "AAA", name: "Alpha", market_value_gbp: 210, gain_gbp: 0 },
        ],
      },
    });

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    expect(
      await screen.findByText("Top holding AAA is 52.50% of your portfolio"),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "Alice Example" }));

    await waitFor(() =>
      expect(screen.queryByText(/Top holding .* is .* of your portfolio/i)).toBeNull(),
    );
  });

  it("falls back to duplication insight when concentration is not triggered", async () => {
    mockAllFetches({
      name: "At a glance",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 100,
          holdings: [
            { ticker: "VWRL.L", units: 1, market_value_gbp: 20, instrument_type: "etf" },
            { ticker: "AAA", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "BBB", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "CCC", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "DDD", units: 1, market_value_gbp: 20, instrument_type: "equity" },
          ],
        },
        {
          owner: "bob",
          account_type: "sipp",
          value_estimate_gbp: 100,
          holdings: [
            { ticker: "VWRL.L", units: 1, market_value_gbp: 20, instrument_type: "etf" },
            { ticker: "EEE", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "FFF", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "GGG", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "HHH", units: 1, market_value_gbp: 20, instrument_type: "equity" },
          ],
        },
      ],
    });

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    expect(
      await screen.findByText("You hold VWRL.L in 2 accounts"),
    ).toBeInTheDocument();
  });

  it("counts duplicated tickers across distinct same-owner account rows", async () => {
    mockAllFetches({
      name: "At a glance",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 100,
          holdings: [
            { ticker: "VWRL.L", units: 1, market_value_gbp: 20, instrument_type: "etf" },
            { ticker: "AAA", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "BBB", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "CCC", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "DDD", units: 1, market_value_gbp: 20, instrument_type: "equity" },
          ],
        },
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 100,
          holdings: [
            { ticker: "VWRL.L", units: 1, market_value_gbp: 20, instrument_type: "etf" },
            { ticker: "EEE", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "FFF", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "GGG", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "HHH", units: 1, market_value_gbp: 20, instrument_type: "equity" },
          ],
        },
      ],
    });

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    expect(
      await screen.findByText("You hold VWRL.L in 2 accounts"),
    ).toBeInTheDocument();
  });

  it("breaks duplication ties by duplicated market value", async () => {
    mockAllFetches({
      name: "At a glance",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 100,
          holdings: [
            { ticker: "AAA", units: 1, market_value_gbp: 5, instrument_type: "equity" },
            { ticker: "BBB", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "CCC", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "DDD", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "EEE", units: 1, market_value_gbp: 35, instrument_type: "equity" },
          ],
        },
        {
          owner: "bob",
          account_type: "sipp",
          value_estimate_gbp: 100,
          holdings: [
            { ticker: "AAA", units: 1, market_value_gbp: 5, instrument_type: "equity" },
            { ticker: "BBB", units: 1, market_value_gbp: 30, instrument_type: "equity" },
            { ticker: "FFF", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "GGG", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "HHH", units: 1, market_value_gbp: 25, instrument_type: "equity" },
          ],
        },
      ],
    });

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    // Use a generous timeout — the insight derivation is async and may take
    // longer than the default 1 000 ms in a busy CI environment.
    expect(
      await screen.findByText("You hold BBB in 2 accounts", {}, { timeout: 5000 }),
    ).toBeInTheDocument();
  });

  it("falls back to cash drag insight when concentration and duplication are absent", async () => {
    mockAllFetches({
      name: "At a glance",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 100,
          holdings: [
            { ticker: "AAA", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "BBB", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "CCC", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "DDD", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "CASH.GBP", units: 20, market_value_gbp: 20, instrument_type: "cash" },
          ],
        },
      ],
    });

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    expect(
      await screen.findByText("20.00% of your portfolio is in cash"),
    ).toBeInTheDocument();
  });

  it("prefers concentration over duplication and cash drag", async () => {
    mockAllFetches({
      name: "At a glance",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 80,
          holdings: [
            { ticker: "AAA", units: 1, market_value_gbp: 70, instrument_type: "equity" },
            { ticker: "VWRL.L", units: 1, market_value_gbp: 10, instrument_type: "etf" },
          ],
        },
        {
          owner: "bob",
          account_type: "sipp",
          value_estimate_gbp: 20,
          holdings: [
            { ticker: "VWRL.L", units: 1, market_value_gbp: 10, instrument_type: "etf" },
            { ticker: "CASH.GBP", units: 10, market_value_gbp: 10, instrument_type: "cash" },
          ],
        },
      ],
    });

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    expect(
      await screen.findByText("Top holding AAA is 70.00% of your portfolio"),
    ).toBeInTheDocument();
    expect(screen.queryByText("You hold VWRL.L in 2 accounts")).toBeNull();
    expect(screen.queryByText("10.00% of your portfolio is in cash")).toBeNull();
  });

  it("suppresses cash balances below the cash-drag threshold", async () => {
    mockAllFetches({
      name: "At a glance",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 100,
          holdings: [
            { ticker: "AAA", units: 1, market_value_gbp: 19.2, instrument_type: "equity" },
            { ticker: "BBB", units: 1, market_value_gbp: 19.2, instrument_type: "equity" },
            { ticker: "CCC", units: 1, market_value_gbp: 19.2, instrument_type: "equity" },
            { ticker: "DDD", units: 1, market_value_gbp: 19.2, instrument_type: "equity" },
            { ticker: "EEE", units: 1, market_value_gbp: 19.2, instrument_type: "equity" },
            { ticker: "CASH.GBP", units: 4, market_value_gbp: 4, instrument_type: "cash" },
          ],
        },
      ],
    });

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    await screen.findByText("At a glance");
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });

  it("shows no insight when concentration, duplication, and cash drag are all absent", async () => {
    mockAllFetches({
      name: "At a glance",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 100,
          holdings: [
            { ticker: "AAA", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "BBB", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "CCC", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "DDD", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "EEE", units: 1, market_value_gbp: 20, instrument_type: "equity" },
          ],
        },
      ],
    });

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    await screen.findByText("At a glance");
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });

  it("ignores duplicated cash tickers when choosing the duplication insight", async () => {
    mockAllFetches({
      name: "At a glance",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 50,
          holdings: [
            { ticker: "AAA", units: 1, market_value_gbp: 16, instrument_type: "equity" },
            { ticker: "BBB", units: 1, market_value_gbp: 16, instrument_type: "equity" },
            { ticker: "CCC", units: 1, market_value_gbp: 16, instrument_type: "equity" },
            { ticker: "CASH.GBP", units: 2, market_value_gbp: 2, instrument_type: "cash" },
          ],
        },
        {
          owner: "bob",
          account_type: "sipp",
          value_estimate_gbp: 50,
          holdings: [
            { ticker: "DDD", units: 1, market_value_gbp: 16, instrument_type: "equity" },
            { ticker: "EEE", units: 1, market_value_gbp: 16, instrument_type: "equity" },
            { ticker: "FFF", units: 1, market_value_gbp: 16, instrument_type: "equity" },
            { ticker: "CASH.GBP", units: 2, market_value_gbp: 2, instrument_type: "cash" },
          ],
        },
      ],
    });

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    await screen.findByText("At a glance");
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });

  const locales = ["en", "fr", "de", "es", "pt", "it"] as const;

  it.each(locales)("renders select group message in %s", async (lng) => {
    await act(async () => {
      await i18n.changeLanguage(lng);
    });
    renderWithConfig(<GroupPortfolioView slug="" owners={ownerFixtures} />);
    expect(await screen.findByText(i18n.t("group.select"))).toBeInTheDocument();
  });

  it.each(locales)("renders error message in %s", async (lng) => {
    await act(async () => {
      await i18n.changeLanguage(lng);
    });
    vi.spyOn(global, "fetch").mockRejectedValueOnce(new Error("boom"));
    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);
    await waitFor(() =>
      screen.getByText(`${i18n.t("common.error")}: boom`)
    );
  });

  it.each(locales)("renders loading message in %s", async (lng) => {
    await act(async () => {
      await i18n.changeLanguage(lng);
    });
    vi.spyOn(global, "fetch").mockImplementation(
      () => new Promise(() => {})
    );
    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);
    expect(screen.getByText(i18n.t("common.loading"))).toBeInTheDocument();
  });

  it("renders metrics error message", async () => {
    const mockPortfolio = {
      name: "At a glance",
      accounts: [],
    };

    const fetchMock = mockAllFetches(mockPortfolio);
    const originalImpl = fetchMock.getMockImplementation();
    fetchMock.mockImplementation((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      if (
        url.includes("alpha-vs-benchmark") ||
        url.includes("tracking-error") ||
        url.includes("max-drawdown")
      ) {
        return Promise.reject(new Error("boom"));
      }
      return originalImpl ? originalImpl(input) : Promise.resolve({
        ok: true,
        json: async () => mockPortfolio,
      } as Response);
    });

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    await waitFor(() =>
      screen.getByText(`${i18n.t("common.error")}: boom`)
    );
  });

  it("renders whole-percentage metrics returned by the API", async () => {
    const mockPortfolio = { name: "At a glance", accounts: [] };
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    const fetchMock = mockAllFetches(mockPortfolio, {
      metrics: {
        alpha: 3.44,
        trackingError: 2.5,
        maxDrawdown: -12.34,
      },
    });

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([input]) =>
          toUrlString(input as RequestInfo | URL).includes("/alpha"),
        ),
      ).toBe(true),
    );

    const alphaLabel = await screen.findByText("Alpha vs Benchmark");
    await waitFor(() =>
      expect(within(alphaLabel.parentElement!).getByText("3.44%"))
        .toBeInTheDocument(),
    );

    const teLabel = await screen.findByText("Tracking Error");
    await waitFor(() =>
      expect(within(teLabel.parentElement!).getByText("2.50%"))
        .toBeInTheDocument(),
    );

    const mdLabel = await screen.findByText("Max Drawdown");
    await waitFor(() =>
      expect(within(mdLabel.parentElement!).getByText("-12.34%"))
        .toBeInTheDocument(),
    );

    expect(warnSpy).not.toHaveBeenCalled();
    warnSpy.mockRestore();
  });

  it("shows N/A for invalid performance metrics", async () => {
    const mockPortfolio = { name: "At a glance", accounts: [] };
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    mockAllFetches(mockPortfolio, {
      metrics: {
        alpha: null,
        trackingError: null,
        maxDrawdown: null,
      },
    });

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    const alphaLabel = await screen.findByText("Alpha vs Benchmark");
    within(alphaLabel.parentElement!).getByText("N/A");
    const teLabel = await screen.findByText("Tracking Error");
    within(teLabel.parentElement!).getByText("N/A");
    const mdLabel = await screen.findByText("Max Drawdown");
    within(mdLabel.parentElement!).getByText("N/A");
    expect(warnSpy).not.toHaveBeenCalled();
    warnSpy.mockRestore();
  });
});
