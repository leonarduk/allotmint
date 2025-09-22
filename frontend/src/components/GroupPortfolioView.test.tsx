import { render, screen, waitFor, act, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { GroupPortfolioView } from "./GroupPortfolioView";
import i18n from "../i18n";
import { configContext, type AppConfig } from "../ConfigContext";
import { useState } from "react";
import * as api from "../api";
vi.mock("./TopMoversSummary", () => ({
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

const renderWithConfig = (ui: React.ReactElement) => render(<TestProvider>{ui}</TestProvider>);

const instrumentKey = (owner?: string | null, account?: string | null) =>
  `${owner ?? ""}::${account ?? ""}`;

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
      const account = parsed.searchParams.get("account");
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
    if (url.includes("alpha-vs-benchmark")) {
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
      json: async () => portfolio,
    } as Response);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
};

describe("GroupPortfolioView", () => {
  it("shows per-owner totals with percentages in relative view", async () => {
    const mockPortfolio = {
      name: "All owners combined",
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

    renderWithConfig(<GroupPortfolioView slug="all" />);

    await waitFor(() => expect(screen.getAllByText("alice").length).toBeGreaterThan(0));

    const toggle = screen.getAllByLabelText('Relative view')[0];
    await userEvent.click(toggle);

    const ownerTable = screen
      .getAllByRole("table")
      .find((table) => within(table).queryByText("Owner"));
    expect(ownerTable).toBeTruthy();
    expect(within(ownerTable!).getByText("alice")).toBeInTheDocument();
    expect(within(ownerTable!).getByText("bob")).toBeInTheDocument();
    expect(within(ownerTable!).getByText("66.67%")).toBeInTheDocument();
    expect(within(ownerTable!).getByText("25.00%")).toBeInTheDocument();
    expect(within(ownerTable!).getByText("-4.76%")).toBeInTheDocument();
    expect(screen.queryByText("Total Value")).toBeNull();
  });

  it("renders instrument type pie chart", async () => {
    const mockPortfolio = {
      name: "All owners combined",
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

    render(<GroupPortfolioView slug="all" />);

    await waitFor(() => {
      const containers = document.querySelectorAll(
        ".recharts-responsive-container",
      );
      expect(containers.length).toBeGreaterThan(0);
    });
  });

  it("switches instrument rows across owner and account tabs", async () => {
    const mockPortfolio = {
      name: "All owners combined",
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

    renderWithConfig(<GroupPortfolioView slug="all" />);

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([input]) =>
          toUrlString(input as RequestInfo | URL).endsWith("/instruments"),
        ),
      ).toBe(true),
    );
    expect(screen.queryByRole("tab", { name: "All accounts" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "alice" }));

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
          toUrlString(input as RequestInfo | URL).includes("account=isa"),
        ),
      ).toBe(true),
    );
    expect(screen.getByRole("tab", { name: "isa" })).toHaveAttribute("aria-selected", "true");

    await userEvent.click(screen.getByRole("tab", { name: "bob" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([input]) =>
          toUrlString(input as RequestInfo | URL).includes("owner=bob"),
        ),
      ).toBe(true),
    );
  });

  it("calls onSelectMember when owner name clicked", async () => {
    const mockPortfolio = {
      name: "All owners combined",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 100,
          holdings: [],
        },
      ],
    };

    mockAllFetches(mockPortfolio);

    const handler = vi.fn();
    render(<GroupPortfolioView slug="all" onSelectMember={handler} />);

    const summaryTable = (await screen.findAllByRole("table")).find((table) =>
      within(table).queryByText("Owner"),
    );
    expect(summaryTable).toBeTruthy();

    const ownerCell = within(summaryTable!).getByText("alice");
    await act(async () => {
      await userEvent.click(ownerCell);
    });

    expect(handler).toHaveBeenCalledWith("alice");
  });


  const locales = ["en", "fr", "de", "es", "pt", "it"] as const;

  it.each(locales)("renders select group message in %s", async (lng) => {
    await act(async () => {
      await i18n.changeLanguage(lng);
    });
    render(<GroupPortfolioView slug="" />);
    expect(await screen.findByText(i18n.t("group.select"))).toBeInTheDocument();
  });

  it.each(locales)("renders error message in %s", async (lng) => {
    await act(async () => {
      await i18n.changeLanguage(lng);
    });
    vi.spyOn(global, "fetch").mockRejectedValueOnce(new Error("boom"));
    render(<GroupPortfolioView slug="all" />);
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
    render(<GroupPortfolioView slug="all" />);
    expect(screen.getByText(i18n.t("common.loading"))).toBeInTheDocument();
  });

  it("renders metrics error message", async () => {
    const mockPortfolio = {
      name: "All owners combined",
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

    renderWithConfig(<GroupPortfolioView slug="all" />);

    await waitFor(() =>
      screen.getByText(`${i18n.t("common.error")}: boom`)
    );
  });

  it("shows N/A for invalid performance metrics", async () => {
    const mockPortfolio = { name: "All owners combined", accounts: [] };
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    mockAllFetches(mockPortfolio, {
      metrics: {
        alpha: null,
        trackingError: null,
        maxDrawdown: null,
      },
    });

    renderWithConfig(<GroupPortfolioView slug="all" />);

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
