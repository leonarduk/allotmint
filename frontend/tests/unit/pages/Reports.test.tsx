import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { configContext } from "@/ConfigContext";

const mockGetOwners = vi.hoisted(() => vi.fn());
const mockListTemplates = vi.hoisted(() => vi.fn());

vi.mock("@/api", () => ({
  API_BASE: "http://test",
  getOwners: mockGetOwners,
  getGroups: vi.fn(),
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
}));

vi.mock("@/api/reports", () => ({
  listReportTemplates: mockListTemplates,
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

const builtinTemplate = {
  template_id: "performance-summary",
  name: "Performance summary",
  description: "Portfolio performance overview",
  builtin: true,
  sections: [
    {
      id: "metrics",
      title: "Performance metrics",
      description: null,
      source: "performance.metrics",
      columns: [
        { key: "metric", label: "Metric", type: "string" },
        { key: "value", label: "Value", type: "number" },
        { key: "units", label: "Units", type: "string" },
      ],
    },
  ],
} as const;

const customTemplate = {
  template_id: "custom-holdings",
  name: "Custom holdings",
  description: "Snapshot of holdings with status metadata",
  builtin: false,
  sections: [
    {
      id: "holdings",
      title: "Holdings",
      description: null,
      source: "allocation",
      columns: [
        { key: "ticker", label: "Ticker", type: "string" },
        { key: "name", label: "Name", type: "string" },
        { key: "value", label: "Value", type: "number" },
        { key: "currency", label: "Currency", type: "string" },
        { key: "status", label: "Status", type: "string" },
      ],
    },
  ],
} as const;

describe("Reports page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
    mockListTemplates.mockResolvedValue([builtinTemplate, customTemplate]);
  });

  async function renderReports(initialEntries: string[] = ["/reports"]) {
    const { default: Reports } = await import("@/pages/Reports");
    return render(
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
        <MemoryRouter initialEntries={initialEntries}>
          <Reports />
        </MemoryRouter>
      </configContext.Provider>,
    );
  }

  it("renders the reports catalog with template metadata", async () => {
    await renderReports();

    expect(
      await screen.findByRole("radio", {
        name: "Select Performance summary template",
      }),
    ).toBeChecked();

    expect(screen.getByText("Performance summary")).toBeInTheDocument();
    expect(
      screen.getByText("3 fields: Metric, Value, Units"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "5 fields: Ticker, Name, Value, Currency +1 more field",
      ),
    ).toBeInTheDocument();
  });

  it("switches selection when choosing a different template", async () => {
    await renderReports();

    const builtinRadio = await screen.findByRole("radio", {
      name: "Select Performance summary template",
    });
    const customRadio = await screen.findByRole("radio", {
      name: "Select Custom holdings template",
    });

    expect(builtinRadio).toBeChecked();
    fireEvent.click(customRadio);
    expect(customRadio).toBeChecked();
    expect(builtinRadio).not.toBeChecked();
  });

  it("includes the chosen template ID in download links", async () => {
    await renderReports();

    const ownerSelect = await screen.findByLabelText(/Owner/i);
    fireEvent.change(ownerSelect, { target: { value: "alex" } });

    const customRadio = await screen.findByRole("radio", {
      name: "Select Custom holdings template",
    });
    fireEvent.click(customRadio);

    const csvLink = await screen.findByRole("link", { name: /Download CSV/i });
    const pdfLink = await screen.findByRole("link", { name: /Download PDF/i });

    expect(csvLink).toHaveAttribute(
      "href",
      "http://test/reports/alex/custom-holdings?format=csv",
    );
    expect(pdfLink).toHaveAttribute(
      "href",
      "http://test/reports/alex/custom-holdings?format=pdf",
    );
  });
});
