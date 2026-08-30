import { render, screen, waitFor, act, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { GroupPortfolioView } from "@/components/GroupPortfolioView";
import i18n from "@/i18n";
import { configContext, type AppConfig } from "@/ConfigContext";
import { useState } from "react";
import * as api from "@/api";
import { MemoryRouter, useLocation } from "react-router-dom";
import type { OwnerSummary } from "@/types";
import { buildPortfolioCsv } from "@/lib/portfolioExport";
vi.mock("@/components/TopMoversSummary", () => ({
  TopMoversSummary: () => <div data-testid="top-movers-summary" />,
}));
vi.mock("@/components/InstrumentDetail", () => ({
  InstrumentDetail: ({ ticker, onClose }: { ticker: string; onClose: () => void }) => (
    <aside>
      <span>Details for {ticker}</span>
      <button type="button" onClick={onClose}>Close instrument details</button>
    </aside>
  ),
}));

const RECHARTS_DIMENSION_WARNING_PATTERN = /width\((?:0|-1)\)|height\((?:0|-1)\)/;

let consoleErrorSpy: ReturnType<typeof vi.spyOn>;
let consoleWarnSpy: ReturnType<typeof vi.spyOn>;

const getRechartsDimensionWarningCalls = (calls: unknown[][]) =>
  calls.filter((args) =>
    args.some(
      (arg) =>
        typeof arg === "string" && RECHARTS_DIMENSION_WARNING_PATTERN.test(arg),
    ),
  );

beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  api.clearGroupInstrumentCache();
  vi
    .spyOn(api, "getCachedGroupInstruments")
    .mockImplementation((slug, filters) => api.getGroupInstruments(slug, filters));
  consoleErrorSpy = vi.spyOn(console, "error");
  consoleWarnSpy = vi.spyOn(console, "warn");
});

afterEach(async () => {
  expect(getRechartsDimensionWarningCalls(consoleErrorSpy.mock.calls)).toEqual(
    [],
  );
  expect(getRechartsDimensionWarningCalls(consoleWarnSpy.mock.calls)).toEqual(
    [],
  );
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
    "trade-compliance": true,
  },
};

const TestProvider = ({ children, config = {} }: { children: React.ReactNode; config?: Partial<AppConfig> }) => {
  const [relativeViewEnabled, setRelativeViewEnabled] = useState(false);
  return (
    <configContext.Provider
      value={{
        ...defaultConfig,
        ...config,
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

const renderWithConfig = (ui: React.ReactElement, config: Partial<AppConfig> = {}) =>
  render(
    <MemoryRouter>
      <TestProvider config={config}>{ui}</TestProvider>
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
    complianceWarnings?: any[];
    complianceFails?: boolean;
    sectorContributions?: any[];
    regionContributions?: any[];
  } = {},
) => {
  const {
    metrics,
    instruments = {},
    complianceWarnings = [],
    complianceFails = false,
    sectorContributions = [],
    regionContributions = [],
  } = options;
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
    if (url.includes("/compliance/")) {
      if (complianceFails) return Promise.reject(new Error("compliance unavailable"));
      return Promise.resolve({ ok: true, json: async () => ({ warnings: complianceWarnings }) } as Response);
    }
    if (url.endsWith("/accounts")) {
      return Promise.resolve({ ok: true, json: async () => ({ status: "created", owner: "alice", account: "isa", currency: "GBP" }) } as Response);
    }
    if (url.includes("/instrument/admin/groups")) {
      return Promise.resolve({
        ok: true,
        json: async () => sectorContributions,
      } as Response);
    }
    if (url.includes("/portfolio/") && url.includes("/sectors")) {
      return Promise.resolve({
        ok: true,
        json: async () => sectorContributions,
      } as Response);
    }
    if (url.includes("/instrument/admin/groupings")) {
      return Promise.resolve({
        ok: true,
        json: async () => regionContributions,
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
    if (url.includes("/portfolio-group/") && url.includes("/sectors")) {
      return Promise.resolve({
        ok: true,
        json: async () => sectorContributions,
      } as Response);
    }
    if (url.includes("/portfolio-group/") && url.includes("/regions")) {
      return Promise.resolve({
        ok: true,
        json: async () => regionContributions,
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
  it("links gain contribution to the matching allocation dimension", async () => {
    mockAllFetches(
      { name: "At a glance", accounts: [] },
      {
        sectorContributions: [{ sector: "Technology", gain_gbp: 25 }],
        regionContributions: [{ region: "UK", gain_gbp: 10 }],
      },
    );
    const user = userEvent.setup();

    renderWithConfig(<GroupPortfolioView slug="family" owners={ownerFixtures} />);

    expect(await screen.findByText("Contribution shows which parts of the portfolio drove gains and losses.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View allocation by industries" })).toHaveAttribute(
      "href",
      "/allocation?group=family&view=sector",
    );

    await user.click(screen.getByRole("button", { name: "Region" }));
    expect(screen.getByRole("link", { name: "View allocation by regions" })).toHaveAttribute(
      "href",
      "/allocation?group=family&view=region",
    );
  });

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

    await userEvent.click(
      await screen.findByRole("tab", { name: "Alice Example" }),
    );

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

    await userEvent.click(
      await screen.findByRole("tab", { name: "Bob Example" }),
    );
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
    // AAA and BBB both appear in 2 accounts (tied on count). BBB has higher total
    // market value (35 vs 10) so it wins. No single ticker exceeds the 20%
    // concentration threshold (BBB = 35/200 = 17.5%), so duplication fires first.
    mockAllFetches({
      name: "At a glance",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 100,
          holdings: [
            { ticker: "AAA", units: 1, market_value_gbp: 5, instrument_type: "equity" },
            { ticker: "BBB", units: 1, market_value_gbp: 15, instrument_type: "equity" },
            { ticker: "CCC", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "DDD", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "EEE", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "FFF", units: 1, market_value_gbp: 20, instrument_type: "equity" },
          ],
        },
        {
          owner: "bob",
          account_type: "sipp",
          value_estimate_gbp: 100,
          holdings: [
            { ticker: "AAA", units: 1, market_value_gbp: 5, instrument_type: "equity" },
            { ticker: "BBB", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "GGG", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "HHH", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "III", units: 1, market_value_gbp: 20, instrument_type: "equity" },
            { ticker: "JJJ", units: 1, market_value_gbp: 15, instrument_type: "equity" },
          ],
        },
      ],
    });

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    // Extended timeout: tie-breaking requires multi-account value aggregation
    // which can exceed the default 1000ms timeout in CI environments.
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
    await waitFor(() => screen.getByText(i18n.t("group.loadError")));
    expect(screen.queryByText(/boom/)).not.toBeInTheDocument();
  });

  it("shows a qualified loading skeleton instead of a bare loading message (#7229)", async () => {
    vi.spyOn(global, "fetch").mockImplementation(
      () => new Promise(() => {})
    );
    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    // The old bare, unqualified "Loading…" string is gone -- replaced by a
    // qualified, screen-reader-announced status plus page-shaped skeletons.
    expect(screen.queryByText(i18n.t("common.loading"))).not.toBeInTheDocument();
    expect(document.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);

    // Exactly one live region for the whole loading page, not one per
    // skeleton placeholder (regression guard: the KPI tiles alone render 5
    // skeleton instances; only one may carry the accessible announcement).
    expect(screen.getAllByRole("status")).toHaveLength(1);
    expect(
      screen.getAllByText(i18n.t("group.loadingPortfolio")).length,
    ).toBeGreaterThan(0);
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

  it("shows owner actions only after selecting an owner", async () => {
    const user = userEvent.setup();
    mockAllFetches({
      name: "At a glance",
      accounts: [{
        owner: "alice",
        account_type: "isa",
        value_estimate_gbp: 100,
        holdings: [{ ticker: "AAA", name: "Alpha", units: 1, market_value_gbp: 100 }],
      }],
    });

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    expect(await screen.findByRole("tab", { name: "Alice Example" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Export portfolio as CSV")).not.toBeInTheDocument();
    expect(screen.queryByText("+ Import CSV")).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Alice Example" }));

    expect(screen.getByLabelText("Export portfolio as CSV")).toBeInTheDocument();
    expect(screen.getByLabelText("Export portfolio as PDF")).toBeInTheDocument();
    expect(screen.getByText("+ Import CSV")).toBeInTheDocument();
    expect(screen.getByText("Add account")).toBeInTheDocument();
  });

  it("builds owner export CSV with every account in source order", () => {
    expect(buildPortfolioCsv({ owner: "alice", as_of: "2026-08-11", accounts: [
      { owner: "alice", account_type: "isa", currency: "GBP", value_estimate_gbp: 10, holdings: [{ ticker: "ISA1", name: "ISA holding", units: 1, market_value_gbp: 10 }] },
      { owner: "alice", account_type: "sipp", currency: "GBP", value_estimate_gbp: 20, holdings: [{ ticker: "SIP1", name: "SIPP holding", units: 2, market_value_gbp: 20 }] },
    ] })).toBe(
      '"owner","as_of","account_type","ticker","name","units","currency","market_value_gbp","gain_gbp","gain_pct"\r\n' +
      '"alice","2026-08-11","isa","ISA1","ISA holding","1","GBP","10","",""\r\n' +
      '"alice","2026-08-11","sipp","SIP1","SIPP holding","2","GBP","20","",""\r\n',
    );
  });

  it("keeps owner tabs but hides exports in family MVP mode", async () => {
    const user = userEvent.setup();
    mockAllFetches({ accounts: [{ owner: "alice", account_type: "isa", value_estimate_gbp: 0, holdings: [] }] });
    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />, { familyMvpEnabled: true });
    const ownerTab = await screen.findByRole("tab", { name: "Alice Example" });
    await user.click(ownerTab);
    expect(ownerTab).toBeInTheDocument();
    expect(screen.queryByLabelText("Export portfolio as CSV")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Export portfolio as PDF")).not.toBeInTheDocument();
    expect(screen.getByText("+ Import CSV")).toBeInTheDocument();
  });

  it("shows owner compliance warnings only after selecting that owner", async () => {
    const user = userEvent.setup();
    mockAllFetches(
      { accounts: [{ owner: "alice", account_type: "isa", value_estimate_gbp: 0, holdings: [] }] },
      { complianceWarnings: [{ code: "limit", message: "Warning" }] },
    );
    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);
    expect(screen.queryByText("View compliance warnings")).not.toBeInTheDocument();
    await user.click(await screen.findByRole("tab", { name: "Alice Example" }));
    expect(await screen.findByRole("link", { name: "View compliance warnings" })).toHaveAttribute("href", "/compliance/alice");
  });

  it("surfaces compliance lookup failures", async () => {
    const user = userEvent.setup();
    mockAllFetches(
      { accounts: [{ owner: "alice", account_type: "isa", value_estimate_gbp: 0, holdings: [] }] },
      { complianceFails: true },
    );
    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);
    await user.click(await screen.findByRole("tab", { name: "Alice Example" }));
    expect(await screen.findByText("Unable to load compliance warnings.")).toHaveAttribute("role", "alert");
  });

  it("does not fetch compliance or show a lookup-failure message when the trade-compliance tab is disabled", async () => {
    const user = userEvent.setup();
    const fetchMock = mockAllFetches(
      { accounts: [{ owner: "alice", account_type: "isa", value_estimate_gbp: 0, holdings: [] }] },
      { complianceFails: true },
    );
    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />, {
      tabs: { ...defaultConfig.tabs, "trade-compliance": false },
    });
    await user.click(await screen.findByRole("tab", { name: "Alice Example" }));
    await waitFor(() => {
      expect(screen.getByLabelText("Export portfolio as CSV")).toBeInTheDocument();
    });
    expect(screen.queryByText("Unable to load compliance warnings.")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/compliance/"))).toBe(false);
  });

  it("refetches after position, import, and account mutations", async () => {
    const user = userEvent.setup();
    Element.prototype.scrollIntoView = vi.fn();
    const fetchMock = mockAllFetches({ accounts: [{ owner: "alice", account_type: "isa", value_estimate_gbp: 0, holdings: [] }] });
    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);
    await user.click(await screen.findByRole("tab", { name: "Alice Example" }));
    const portfolioRequestCount = () => fetchMock.mock.calls.filter(([input]) => {
      const url = toUrlString(input as RequestInfo | URL);
      return url.includes("/portfolio-group/all") && !url.includes("/instruments");
    }).length;
    const initialRequests = portfolioRequestCount();

    await user.click(screen.getByRole("button", { name: /add position/i }));
    const positionForm = screen.getByRole("form", { name: /^add position$/i });
    await user.type(within(positionForm).getByLabelText(/ticker/i), "VWRL");
    await user.type(within(positionForm).getByLabelText(/^units$/i), "1");
    await user.type(within(positionForm).getByLabelText(/price/i), "100");
    await user.click(within(positionForm).getByRole("button", { name: /^add position$/i }));
    await screen.findByRole("tab", { name: "Alice Example" });

    await user.click(screen.getByRole("button", { name: /import csv/i }));
    await user.selectOptions(screen.getByLabelText(/provider/i), "hargreaves");
    await user.upload(screen.getByLabelText(/csv file/i), new File(["ticker,qty\nVWRL,1"], "holdings.csv", { type: "text/csv" }));
    await user.click(screen.getByRole("button", { name: /^import$/i }));
    await screen.findByRole("tab", { name: "Alice Example" });

    await user.click(screen.getByRole("button", { name: /^add account$/i }));
    await user.click(screen.getByRole("button", { name: /^add account$/i }));
    await waitFor(() => expect(portfolioRequestCount()).toBe(initialRequests + 3));
    await new Promise((resolve) => window.setTimeout(resolve, 50));
    expect(portfolioRequestCount()).toBe(initialRequests + 3);
  });

  it("defaults to one aggregated row per ticker while keeping account and category views available", async () => {
    const user = userEvent.setup();
    mockAllFetches({
      name: "At a glance",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 50,
          holdings: [{ ticker: "AAA", units: 1, market_value_gbp: 50 }],
        },
        {
          owner: "alice",
          account_type: "sipp",
          value_estimate_gbp: 75,
          holdings: [{ ticker: "AAA", units: 2, market_value_gbp: 75 }],
        },
      ],
    });

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    expect(await screen.findAllByRole("button", { name: "AAA" })).toHaveLength(1);
    expect(screen.getByRole("radio", { name: "Rollup" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Category" })).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "Flat" }));
    expect(await screen.findAllByRole("button", { name: "AAA" })).toHaveLength(2);
  });

  it("hides the display-mode toggle and keeps flat mode forced in family MVP even with duplicate lots", async () => {
    const mockPortfolio = {
      name: "At a glance",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 50,
          holdings: [{ ticker: "AAA", units: 1, market_value_gbp: 50 }],
        },
        {
          owner: "alice",
          account_type: "sipp",
          value_estimate_gbp: 100,
          holdings: [{ ticker: "AAA", units: 2, market_value_gbp: 100 }],
        },
      ],
    };
    const fetchMock = mockAllFetches(mockPortfolio);

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />, {
      familyMvpEnabled: true,
    });

    // Two distinct lots for the same ticker must render as two rows; a forced
    // rollup would incorrectly collapse them into one aggregated row.
    expect(await screen.findAllByRole("button", { name: "AAA" })).toHaveLength(2);
    expect(screen.queryByRole("radio", { name: "Rollup" })).not.toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "Flat" })).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([input]) =>
        toUrlString(input as RequestInfo | URL).endsWith("/instruments"),
      ),
    ).toBe(false);
  });

  it("falls back to Ungrouped and still shows correct money for a rollup ticker missing instrument enrichment", async () => {
    const user = userEvent.setup();
    const mockPortfolio = {
      name: "At a glance",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 100,
          holdings: [
            { ticker: "AAA", units: 1, market_value_gbp: 60, gain_gbp: 0 },
            { ticker: "BBB", units: 1, market_value_gbp: 40, gain_gbp: 0 },
          ],
        },
      ],
    };
    // BBB is deliberately absent from the instruments payload to simulate a
    // join miss (§3: the row still shows correct money).
    const instruments = {
      [instrumentKey()]: [
        { ticker: "AAA", name: "Alpha", units: 1, market_value_gbp: 60, gain_gbp: 0, grouping: "Equity" },
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

    await user.click(await screen.findByRole("radio", { name: "Category" }));
    await user.click(await screen.findByRole("button", { name: "Toggle Ungrouped" }));
    const bbbRow = (await screen.findByRole("button", { name: "BBB" })).closest("tr")!;
    expect(within(bbbRow).getAllByText("£40.00").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Toggle Equity" }));
    const aaaRow = (await screen.findByRole("button", { name: "AAA" })).closest("tr")!;
    expect(within(aaaRow).getAllByText("£60.00").length).toBeGreaterThan(0);
  });

  it("opens the InstrumentDetail drawer on ticker click without navigating away", async () => {
    const user = userEvent.setup();
    const mockPortfolio = {
      name: "At a glance",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 60,
          holdings: [{ ticker: "ZZZ", units: 1, market_value_gbp: 60 }],
        },
      ],
    };
    mockAllFetches(mockPortfolio);

    const LocationDisplay = () => {
      const location = useLocation();
      return <div data-testid="location-display">{location.pathname}</div>;
    };

    render(
      <MemoryRouter initialEntries={["/portfolio/all"]}>
        <TestProvider>
          <GroupPortfolioView slug="all" owners={ownerFixtures} />
        </TestProvider>
        <LocationDisplay />
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole("button", { name: "ZZZ" }));

    expect(screen.getByText("Details for ZZZ")).toBeInTheDocument();
    expect(screen.getByTestId("location-display")).toHaveTextContent("/portfolio/all");

    await user.click(screen.getByRole("button", { name: "Close instrument details" }));
    expect(screen.queryByText("Details for ZZZ")).not.toBeInTheDocument();
  });

  it("renders family-level charts and metrics only at All family scope, not at owner scope", async () => {
    const mockPortfolio = {
      name: "At a glance",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 100,
          holdings: [
            { ticker: "AAA", units: 1, market_value_gbp: 100, instrument_type: "equity" },
          ],
        },
      ],
    };
    mockAllFetches(mockPortfolio, { metrics: { alpha: 5, trackingError: 2, maxDrawdown: 10 } });

    const { unmount } = render(
      <MemoryRouter initialEntries={["/"]}>
        <TestProvider>
          <GroupPortfolioView slug="all" owners={ownerFixtures} />
        </TestProvider>
      </MemoryRouter>,
    );

    // TopMoversSummary fetches its own data independently of the portfolio
    // call (see #7229) and can resolve before or after it, so it is no
    // longer a reliable signal that the portfolio-derived tiles below have
    // also finished loading -- each assertion waits for its own content.
    expect(await screen.findByTestId("top-movers-summary")).toBeInTheDocument();
    expect(await screen.findByText("Alpha vs Benchmark")).toBeInTheDocument();
    expect(screen.getByText("Tracking Error")).toBeInTheDocument();

    unmount();
    render(
      <MemoryRouter initialEntries={["/?owner=alice"]}>
        <TestProvider>
          <GroupPortfolioView slug="all" owners={ownerFixtures} />
        </TestProvider>
      </MemoryRouter>,
    );

    await screen.findByRole("tab", { name: "Alice Example" });

    expect(screen.queryByTestId("top-movers-summary")).not.toBeInTheDocument();
    expect(screen.queryByText("Alpha vs Benchmark")).not.toBeInTheDocument();
    expect(screen.queryByText("Tracking Error")).not.toBeInTheDocument();
  });

  it("renders owner sector contributions from the owner-scoped endpoint", async () => {
    const getOwnerSectorContributions = vi
      .spyOn(api, "getOwnerSectorContributions")
      .mockResolvedValue([{ sector: "Technology", gain_gbp: 12 }]);
    const fetchMock = mockAllFetches(
      {
        name: "At a glance",
        accounts: [
          { owner: "alice", account_type: "isa", value_estimate_gbp: 100, holdings: [] },
        ],
      },
      {
        sectorContributions: [{ sector: "Technology", gain_gbp: 12 }],
        regionContributions: [{ region: "Europe", gain_gbp: 8 }],
      },
    );

    render(
      <MemoryRouter initialEntries={["/?owner=alice"]}>
        <TestProvider>
          <GroupPortfolioView slug="all" owners={ownerFixtures} />
        </TestProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Technology")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sector" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Region" })).not.toBeInTheDocument();
    expect(screen.queryByText("Europe")).not.toBeInTheDocument();
    expect(getOwnerSectorContributions).toHaveBeenCalledWith(
      "alice",
      { asOf: undefined },
    );
    expect(
      fetchMock.mock.calls.some(([input]) =>
        toUrlString(input).includes("region-contributions"),
      ),
    ).toBe(false);
  });

  it("keeps the current path and unrelated query parameters when changing scope", async () => {
    const user = userEvent.setup();
    mockAllFetches({
      name: "At a glance",
      accounts: [
        { owner: "alice", account_type: "isa", value_estimate_gbp: 100, holdings: [] },
      ],
    });

    const RouteDisplay = () => {
      const location = useLocation();
      return <output data-testid="scope-route">{`${location.pathname}${location.search}`}</output>;
    };

    render(
      <MemoryRouter initialEntries={["/?period=1y"]}>
        <TestProvider>
          <GroupPortfolioView slug="all" owners={ownerFixtures} />
        </TestProvider>
        <RouteDisplay />
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole("tab", { name: "Alice Example" }));
    expect(screen.getByTestId("scope-route")).toHaveTextContent(
      "/?period=1y&owner=alice",
    );

    await user.click(screen.getByRole("tab", { name: "isa" }));
    expect(screen.getByTestId("scope-route")).toHaveTextContent(
      "/?period=1y&owner=alice&account=isa",
    );
  });

  it("removes an invalid account without dropping other URL state", async () => {
    mockAllFetches({
      name: "At a glance",
      accounts: [
        { owner: "alice", account_type: "isa", value_estimate_gbp: 100, holdings: [] },
      ],
    });

    const RouteDisplay = () => {
      const location = useLocation();
      return <output data-testid="scope-route">{`${location.pathname}${location.search}`}</output>;
    };

    render(
      <MemoryRouter
        initialEntries={["/portfolio/all?period=1y&owner=alice&account=invalid"]}
      >
        <TestProvider>
          <GroupPortfolioView slug="all" owners={ownerFixtures} />
        </TestProvider>
        <RouteDisplay />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("scope-route")).toHaveTextContent(
        "/portfolio/all?period=1y&owner=alice",
      ),
    );
  });

  it("falls back to family scope when the URL owner is invalid", async () => {
    mockAllFetches({
      name: "At a glance",
      accounts: [
        { owner: "alice", account_type: "isa", value_estimate_gbp: 100, holdings: [] },
      ],
    });

    const RouteDisplay = () => {
      const location = useLocation();
      return <output data-testid="scope-route">{`${location.pathname}${location.search}`}</output>;
    };

    render(
      <MemoryRouter initialEntries={["/?period=1y&owner=invalid&account=isa"]}>
        <TestProvider>
          <GroupPortfolioView slug="all" owners={ownerFixtures} />
        </TestProvider>
        <RouteDisplay />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("scope-route")).toHaveTextContent("/?period=1y"),
    );
  });

  it("shows the consolidated no-price-history notice once via the embedded holdings table", async () => {
    const mockPortfolio = {
      name: "At a glance",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 100,
          holdings: [
            {
              ticker: "NOHIST.L",
              name: "No History Plc",
              units: 1,
              cost_basis_gbp: 80,
              market_value_gbp: 100,
            },
          ],
        },
      ],
    };
    const fetchMock = mockAllFetches(mockPortfolio);
    const originalFetch = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = toUrlString(input);
      if (url.includes("/instrument/batch")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            instruments: {},
            empty: ["NOHIST.L"],
            unknown: [],
          }),
        } as Response);
      }
      if (url.includes("/instrument/?ticker=")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            prices: [],
            mini: { 7: [], 30: [], 180: [] },
            positions: [],
          }),
        } as Response);
      }
      return originalFetch(input);
    });

    renderWithConfig(<GroupPortfolioView slug="all" owners={ownerFixtures} />);

    // The notice is rendered by HoldingsTable, which GroupPortfolioView embeds
    // in every display mode; exactly one notice must appear (no duplication).
    expect(
      await screen.findByText("1 instrument has no price history"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("1 instrument has no price history")).toHaveLength(1);
  });
});
