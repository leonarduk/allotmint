import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

import { configContext } from "@/ConfigContext";

const mockGetOwners = vi.hoisted(() => vi.fn());
const mockGetGroups = vi.hoisted(() => vi.fn());
const mockUseReportsCatalog = vi.hoisted(() => vi.fn());

vi.mock("@/api", () => ({
  API_BASE: "http://test",
  getOwners: mockGetOwners,
  getGroups: mockGetGroups,
  getGroupInstruments: vi.fn().mockResolvedValue([]),
  getPortfolio: vi.fn(),
  refreshPrices: vi.fn(),
  getAlerts: vi.fn().mockResolvedValue([]),
  getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
  getCompliance: vi
    .fn()
    .mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
  getTimeseries: vi.fn().mockResolvedValue([]),
  saveTimeseries: vi.fn(),
  refetchTimeseries: vi.fn(),
  rebuildTimeseriesCache: vi.fn(),
  getTradingSignals: vi.fn().mockResolvedValue([]),
  getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
  listTimeseries: vi.fn().mockResolvedValue([]),
  getReportsCatalog: vi.fn(),
}));

vi.mock("@/hooks/useReportsCatalog", () => ({
  useReportsCatalog: mockUseReportsCatalog,
}));

const allTabs = {
  group: true,
  owner: true,
  instrument: true,
  performance: true,
  transactions: true,
  trading: true,
  screener: true,
  timeseries: true,
  watchlist: true,
  allocation: true,
  market: true,
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
};

describe("Reports page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    const builtIn = [
      {
        id: "builtin-holdings",
        name: "Holdings Overview",
        description: "Positions summary",
        fields: ["Account", "Value"],
      },
    ];
    const custom = [
      {
        id: "custom-cashflow",
        name: "Cash Flow Detail",
        description: "Custom template",
        fields: ["Date", "Amount"],
      },
    ];
    mockUseReportsCatalog.mockReturnValue({
      builtIn,
      custom,
      templates: [
        { ...builtIn[0], source: "built-in" as const },
        { ...custom[0], source: "custom" as const },
      ],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });
  });

  it("renders catalog entries and defaults to the first template", async () => {
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
    mockGetGroups.mockResolvedValue([]);

    window.history.pushState({}, "", "/reports");
    const { default: Reports } = await import("@/pages/Reports");

    render(
      <configContext.Provider
        value={{
          theme: "system",
          relativeViewEnabled: false,
          tabs: allTabs,
          disabledTabs: [],
          refreshConfig: vi.fn(),
          setRelativeViewEnabled: () => {},
          baseCurrency: "GBP",
          setBaseCurrency: () => {},
        }}
      >
        <MemoryRouter initialEntries={["/reports"]}>
          <Reports />
        </MemoryRouter>
      </configContext.Provider>
    );

    await screen.findByText(/Built-in templates/i);
    const defaultTemplate = screen.getByLabelText(/Holdings Overview/);
    expect(defaultTemplate).toBeChecked();
    expect(screen.getByText("Positions summary")).toBeInTheDocument();
    expect(screen.getByText("Account")).toBeInTheDocument();
    expect(screen.getByText("Value")).toBeInTheDocument();
  });

  it("updates download links with the selected template", async () => {
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
    mockGetGroups.mockResolvedValue([]);

    window.history.pushState({}, "", "/reports");
    const { default: Reports } = await import("@/pages/Reports");

    render(
      <configContext.Provider
        value={{
          theme: "system",
          relativeViewEnabled: false,
          tabs: allTabs,
          disabledTabs: [],
          refreshConfig: vi.fn(),
          setRelativeViewEnabled: () => {},
          baseCurrency: "GBP",
          setBaseCurrency: () => {},
        }}
      >
        <MemoryRouter initialEntries={["/reports"]}>
          <Reports />
        </MemoryRouter>
      </configContext.Provider>
    );

    const select = await screen.findByLabelText(/owner/i);
    expect(screen.getByText(/Select an owner and template/i)).toBeInTheDocument();

    fireEvent.change(select, { target: { value: "alex" } });

    const csv = await screen.findByRole("link", { name: /Download CSV/i });
    expect(csv).toHaveAttribute(
      "href",
      "http://test/reports/alex?template=builtin-holdings&format=csv"
    );

    const customTemplate = screen.getByLabelText(/Cash Flow Detail/);
    fireEvent.click(customTemplate);

    await waitFor(() => {
      expect(csv).toHaveAttribute(
        "href",
        "http://test/reports/alex?template=custom-cashflow&format=csv"
      );
    });
    const pdf = screen.getByRole("link", { name: /Download PDF/i });
    expect(pdf).toHaveAttribute(
      "href",
      "http://test/reports/alex?template=custom-cashflow&format=pdf"
    );
  });

  it("shows message when no owners", async () => {
    mockGetOwners.mockResolvedValue([]);
    mockGetGroups.mockResolvedValue([]);
    mockUseReportsCatalog.mockReturnValue({
      builtIn: [],
      custom: [],
      templates: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    window.history.pushState({}, "", "/reports");
    const { default: Reports } = await import("@/pages/Reports");

    render(
      <configContext.Provider
        value={{
          theme: "system",
          relativeViewEnabled: false,
          tabs: allTabs,
          disabledTabs: [],
          refreshConfig: vi.fn(),
          setRelativeViewEnabled: () => {},
          baseCurrency: "GBP",
          setBaseCurrency: () => {},
        }}
      >
        <MemoryRouter initialEntries={["/reports"]}>
          <Reports />
        </MemoryRouter>
      </configContext.Provider>
    );

    const message = await screen.findByText(
      /No owners available—check backend connection/i
    );
    expect(message).toBeInTheDocument();
    expect(screen.queryByLabelText(/owner/i)).not.toBeInTheDocument();
    expect(screen.getByText(/No report templates available/i)).toBeInTheDocument();
  });
});

