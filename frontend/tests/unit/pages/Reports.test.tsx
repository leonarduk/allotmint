import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { configContext } from "@/ConfigContext";

const mockGetOwners = vi.hoisted(() => vi.fn());
const mockListTemplates = vi.hoisted(() => vi.fn());
const mockDeleteTemplate = vi.hoisted(() => vi.fn());

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
  deleteReportTemplate: mockDeleteTemplate,
}));

const mockCompleteTrackedChore = vi.hoisted(() => vi.fn());

vi.mock("@/choreCompletion", () => ({
  completeTrackedChore: mockCompleteTrackedChore,
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
          reportingCurrency: "GBP",
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

  it("styles template cards with theme variables instead of fixed greys", async () => {
    const { container } = await renderReports();

    const radio = await screen.findByRole("radio", {
      name: "Select Performance summary template",
    });
    const card = radio.closest("label");
    expect(card).toHaveClass(
      "bg-[var(--surface-card-bg)]",
      "text-[var(--surface-card-color)]",
    );
    expect(screen.getByText("3 fields: Metric, Value, Units")).toHaveClass(
      "text-[var(--surface-muted-color)]",
    );
    expect(container.innerHTML).not.toMatch(/\b(?:text|border)-gray-\d+/);
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

  it("defaults to the signed-in user's owner rather than owners[0] (#10753)", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", email: "alex@example.com", accounts: [] },
      { owner: "steve", email: "steve@example.com", accounts: [] },
    ]);
    const { AuthContext } = await import("@/AuthContext");
    const { default: Reports } = await import("@/pages/Reports");
    render(
      <AuthContext.Provider
        value={{
          user: { email: "steve@example.com" },
          setUser: () => {},
          logout: null,
          setLogout: () => {},
          demoReadOnly: false,
          setDemoReadOnly: () => {},
        }}
      >
        <MemoryRouter>
          <Reports />
        </MemoryRouter>
      </AuthContext.Provider>,
    );

    const csvLink = await screen.findByRole("link", { name: /Download CSV/i });
    expect(csvLink.getAttribute("href")).toContain("/reports/steve/");
    expect(screen.getByLabelText(/Owner/i)).toHaveValue("steve");
  });

  it("lets the app-selected route owner win over the signed-in user (#10753)", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", email: "alex@example.com", accounts: [] },
      { owner: "steve", email: "steve@example.com", accounts: [] },
    ]);
    const { AuthContext } = await import("@/AuthContext");
    const { RouteContext } = await import("@/contexts/route");
    const { default: Reports } = await import("@/pages/Reports");
    render(
      <AuthContext.Provider
        value={{
          user: { email: "steve@example.com" },
          setUser: () => {},
          logout: null,
          setLogout: () => {},
          demoReadOnly: false,
          setDemoReadOnly: () => {},
        }}
      >
        <RouteContext.Provider
          value={{
            mode: "reports",
            setMode: () => {},
            selectedOwner: "alex",
            setSelectedOwner: () => {},
            selectedGroup: "",
            setSelectedGroup: () => {},
          }}
        >
          <MemoryRouter>
            <Reports />
          </MemoryRouter>
        </RouteContext.Provider>
      </AuthContext.Provider>,
    );

    const csvLink = await screen.findByRole("link", { name: /Download CSV/i });
    expect(csvLink.getAttribute("href")).toContain("/reports/alex/");
  });

  it("routes a picker choice through the app-level owner (#10753)", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", accounts: [] },
      { owner: "steve", accounts: [] },
    ]);
    const setSelectedOwner = vi.fn();
    const { RouteContext } = await import("@/contexts/route");
    const { default: Reports } = await import("@/pages/Reports");
    render(
      <RouteContext.Provider
        value={{
          mode: "reports",
          setMode: () => {},
          selectedOwner: "alex",
          setSelectedOwner,
          selectedGroup: "",
          setSelectedGroup: () => {},
        }}
      >
        <MemoryRouter>
          <Reports />
        </MemoryRouter>
      </RouteContext.Provider>,
    );

    const ownerSelect = await screen.findByLabelText(/Owner/i);
    await screen.findByRole("option", { name: "steve" });
    fireEvent.change(ownerSelect, { target: { value: "steve" } });
    expect(setSelectedOwner).toHaveBeenCalledWith("steve");
  });

  it("falls back to owners[0] when the signed-in user matches no owner", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", email: "alex@example.com", accounts: [] },
      { owner: "steve", email: "steve@example.com", accounts: [] },
    ]);
    const { AuthContext } = await import("@/AuthContext");
    const { default: Reports } = await import("@/pages/Reports");
    render(
      <AuthContext.Provider
        value={{
          user: { email: "visitor@example.com" },
          setUser: () => {},
          logout: null,
          setLogout: () => {},
          demoReadOnly: false,
          setDemoReadOnly: () => {},
        }}
      >
        <MemoryRouter>
          <Reports />
        </MemoryRouter>
      </AuthContext.Provider>,
    );

    const csvLink = await screen.findByRole("link", { name: /Download CSV/i });
    expect(csvLink.getAttribute("href")).toContain("/reports/alex/");
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

  it("completes the 'run a report' chore when a live download link is clicked", async () => {
    await renderReports();

    const ownerSelect = await screen.findByLabelText(/Owner/i);
    fireEvent.change(ownerSelect, { target: { value: "alex" } });

    const csvLink = await screen.findByRole("link", { name: /Download CSV/i });
    fireEvent.click(csvLink);

    expect(mockCompleteTrackedChore).toHaveBeenCalledWith("run_a_report");
  });

  it("links to the template creator from /reports (#10914)", async () => {
    await renderReports();

    expect(
      await screen.findByRole("link", { name: "Create template" }),
    ).toHaveAttribute("href", "/reports/new");
  });

  it("confirms and selects a template saved on /reports/new", async () => {
    const { default: Reports } = await import("@/pages/Reports");
    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: "/reports",
            state: {
              createdTemplate: {
                template_id: "custom-holdings",
                name: "Custom holdings",
              },
            },
          },
        ]}
      >
        <Reports />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Saved template Custom holdings."),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("radio", {
        name: "Select Custom holdings template",
      }),
    ).toBeChecked();
  });

  it("offers delete only on custom templates", async () => {
    await renderReports();

    expect(
      await screen.findByRole("button", {
        name: "Delete Custom holdings template",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", {
        name: "Delete Performance summary template",
      }),
    ).not.toBeInTheDocument();
  });

  it("deletes a custom template after confirmation and reloads the catalogue", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    mockDeleteTemplate.mockResolvedValue(undefined);
    await renderReports();

    const button = await screen.findByRole("button", {
      name: "Delete Custom holdings template",
    });
    mockListTemplates.mockResolvedValue([builtinTemplate]);
    fireEvent.click(button);

    expect(mockDeleteTemplate).toHaveBeenCalledWith("custom-holdings");
    expect(
      await screen.findByText("Deleted template Custom holdings."),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.queryByRole("radio", { name: "Select Custom holdings template" }),
      ).not.toBeInTheDocument(),
    );
    confirmSpy.mockRestore();
  });

  it("does nothing when the delete is not confirmed", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    await renderReports();

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Delete Custom holdings template",
      }),
    );

    expect(mockDeleteTemplate).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it("shows the error when a delete fails", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    mockDeleteTemplate.mockRejectedValue(new Error("Template not found"));
    await renderReports();

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Delete Custom holdings template",
      }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Template not found",
    );
    expect(
      screen.getByRole("radio", { name: "Select Custom holdings template" }),
    ).toBeInTheDocument();
    confirmSpy.mockRestore();
  });
});
