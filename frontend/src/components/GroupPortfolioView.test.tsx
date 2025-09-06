import { render, screen, waitFor, act, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { GroupPortfolioView } from "./GroupPortfolioView";
import i18n from "../i18n";
import { configContext, type AppConfig } from "../ConfigContext";
import { useState } from "react";
vi.mock("./TopMoversSummary", () => ({
  TopMoversSummary: () => <div data-testid="top-movers-summary" />,
}));

beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

afterEach(async () => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
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
    owner: true,
    instrument: true,
    performance: true,
    transactions: true,
    trading: true,
    screener: true,
    timeseries: true,
    watchlist: true,
    movers: true,
    instrumentadmin: true,
    dataadmin: true,
    virtual: true,
    support: true,
    settings: true,
    profile: true,
    reports: true,
    scenario: true,
    logs: true,
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

const mockAllFetches = (
  portfolio: any,
  metrics: { alpha?: any; trackingError?: any; maxDrawdown?: any } = {},
) => {
  const { alpha = 0, trackingError = 0, maxDrawdown = 0 } = metrics;
  const fetchMock = vi.fn((input: RequestInfo) => {
    const url = typeof input === "string" ? input : input.url;
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

    await waitFor(() => screen.getByText("alice"));

    const toggle = screen.getAllByLabelText('Relative view')[0];
    await userEvent.click(toggle);

    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.getByText("bob")).toBeInTheDocument();
    expect(screen.getByText("66.67%")).toBeInTheDocument();
    expect(screen.getByText("25.00%")).toBeInTheDocument();
    expect(screen.getByText("-4.76%")).toBeInTheDocument();
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

    await waitFor(() => screen.getAllByText("Equity"));

    expect(screen.getAllByText("Equity").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Cash").length).toBeGreaterThan(0);
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

    await screen.findAllByText("alice");

    await act(async () => {
      await userEvent.click(screen.getAllByText("alice")[0]);
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

  it("updates totals when accounts are toggled", async () => {
    await act(async () => {
      await i18n.changeLanguage("en");
    });
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
          owner: "bob",
          account_type: "isa",
          value_estimate_gbp: 200,
          holdings: [],
        },
      ],
    };

    mockAllFetches(mockPortfolio);


    render(<GroupPortfolioView slug="all" />);

    await waitFor(() => screen.getByLabelText(/alice isa/i));

    await waitFor(() =>
      expect(screen.getAllByText("Total Value")[0].nextElementSibling).toHaveTextContent(
        "£300.00",
      ),
    );

    const bobCheckbox = screen.getByLabelText(/bob isa/i);
    await act(async () => {
      await userEvent.click(bobCheckbox);
    });
    await waitFor(() =>
      expect(screen.getAllByText("Total Value")[0].nextElementSibling).toHaveTextContent(
        "£100.00",
      ),
    );
  });

  it("shows N/A for invalid performance metrics", async () => {
    const mockPortfolio = { name: "All owners combined", accounts: [] };
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    mockAllFetches(mockPortfolio, {
      alpha: 2,
      trackingError: null,
      maxDrawdown: Infinity,
    });

    renderWithConfig(<GroupPortfolioView slug="all" />);

    const alphaLabel = await screen.findByText("Alpha vs Benchmark");
    within(alphaLabel.parentElement!).getByText("N/A");
    const teLabel = await screen.findByText("Tracking Error");
    within(teLabel.parentElement!).getByText("N/A");
    const mdLabel = await screen.findByText("Max Drawdown");
    within(mdLabel.parentElement!).getByText("N/A");

    expect(warnSpy.mock.calls.length).toBeGreaterThanOrEqual(3);
  });
});
