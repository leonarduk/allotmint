import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { configContext } from "@/ConfigContext";

const mockGetOwners = vi.hoisted(() => vi.fn());
const mockGetGroups = vi.hoisted(() => vi.fn());
const mockListTemplates = vi.hoisted(() => vi.fn());
const mockCreateTemplate = vi.hoisted(() => vi.fn());
const mockUpdateTemplate = vi.hoisted(() => vi.fn());
const mockDeleteTemplate = vi.hoisted(() => vi.fn());
const mockGetTemplate = vi.hoisted(() => vi.fn());

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
}));

vi.mock("@/api/reports", () => ({
  listReportTemplates: mockListTemplates,
  createReportTemplate: mockCreateTemplate,
  updateReportTemplate: mockUpdateTemplate,
  deleteReportTemplate: mockDeleteTemplate,
  getReportTemplate: mockGetTemplate,
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
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
    mockGetGroups.mockResolvedValue([]);
    mockListTemplates.mockResolvedValue([]);
    mockCreateTemplate.mockResolvedValue({
      id: "new-id",
      name: "Created template",
      metrics: ["performance"],
      columns: ["owner", "ticker"],
      filters: [],
    });
    mockUpdateTemplate.mockResolvedValue({
      id: "tpl-1",
      name: "Updated template",
      metrics: ["performance"],
      columns: ["owner", "ticker"],
      filters: [],
    });
    mockDeleteTemplate.mockResolvedValue(undefined);
    mockGetTemplate.mockResolvedValue({
      id: "tpl-1",
      name: "Loaded template",
      metrics: ["performance"],
      columns: ["owner", "ticker"],
      filters: [],
    });
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

  it("renders owner download links when owner selected", async () => {
    await renderReports();

    const select = await screen.findByLabelText(/owner/i);
    fireEvent.change(select, { target: { value: "alex" } });

    const csv = await screen.findByText(/Download CSV/i);
    expect(csv).toHaveAttribute("href", expect.stringContaining("/reports/alex"));
  });

  it("creates a report template via the builder route", async () => {
    mockCreateTemplate.mockResolvedValue({
      id: "tpl-2",
      name: "Quarterly Overview",
      metrics: ["performance"],
      columns: ["owner", "ticker", "gain_pct"],
      filters: [],
    });

    await renderReports(["/reports/new"]);

    const nameInput = await screen.findByLabelText(/Template name/i);
    fireEvent.change(nameInput, { target: { value: "Quarterly Overview" } });

    const description = screen.getByLabelText(/Description/);
    fireEvent.change(description, { target: { value: "All owners" } });

    const createButton = screen.getByRole("button", { name: /Create template/i });
    fireEvent.click(createButton);

    await waitFor(() => {
      expect(mockCreateTemplate).toHaveBeenCalledWith({
        name: "Quarterly Overview",
        description: "All owners",
        metrics: expect.any(Array),
        columns: expect.any(Array),
        filters: [],
      });
    });

    expect(await screen.findByText("Quarterly Overview")).toBeInTheDocument();
  });

  it("updates an existing template when editing", async () => {
    mockListTemplates.mockResolvedValue([
      {
        id: "tpl-1",
        name: "Performance pack",
        metrics: ["performance", "risk"],
        columns: ["owner", "ticker", "gain_pct"],
        filters: [],
      },
    ]);

    await renderReports(["/reports/tpl-1/edit"]);

    const nameInput = await screen.findByLabelText(/Template name/i);
    fireEvent.change(nameInput, { target: { value: "Updated template" } });

    const saveButton = screen.getByRole("button", { name: /Save changes/i });
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(mockUpdateTemplate).toHaveBeenCalledWith("tpl-1", {
        name: "Updated template",
        description: undefined,
        metrics: expect.any(Array),
        columns: expect.any(Array),
        filters: [],
      });
    });
  });

  it("deletes an existing template from the builder", async () => {
    mockListTemplates.mockResolvedValue([
      {
        id: "tpl-1",
        name: "Performance pack",
        metrics: ["performance"],
        columns: ["owner", "ticker"],
        filters: [],
      },
    ]);

    await renderReports(["/reports/tpl-1/edit"]);

    const deleteButton = await screen.findByRole("button", { name: /Delete template/i });
    fireEvent.click(deleteButton);

    await waitFor(() => {
      expect(mockDeleteTemplate).toHaveBeenCalledWith("tpl-1");
    });
  });
});
