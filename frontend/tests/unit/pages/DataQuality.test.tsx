import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { act } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import en from "@/locales/en/translation.json";
import DataQuality from "@/pages/DataQuality";
import { configContext, type ConfigContextValue } from "@/ConfigContext";

const mockGetDataQualityTimeseries = vi.hoisted(() => vi.fn());
const mockGetDataQualityIssues = vi.hoisted(() => vi.fn());
const mockFixDataQualityIssue = vi.hoisted(() => vi.fn());
const mockFixDataQualityBatch = vi.hoisted(() => vi.fn());
const mockDedupeDataQualitySeries = vi.hoisted(() => vi.fn());
const mockGetDataQualityAudit = vi.hoisted(() => vi.fn());
const mockUndoDataQualityAudit = vi.hoisted(() => vi.fn());

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    getDataQualityTimeseries: mockGetDataQualityTimeseries,
    getDataQualityIssues: mockGetDataQualityIssues,
    fixDataQualityIssue: mockFixDataQualityIssue,
    fixDataQualityBatch: mockFixDataQualityBatch,
    dedupeDataQualitySeries: mockDedupeDataQualitySeries,
    getDataQualityAudit: mockGetDataQualityAudit,
    undoDataQualityAudit: mockUndoDataQualityAudit,
  };
});

const baseConfig: ConfigContextValue = {
  configLoaded: true,
  relativeViewEnabled: false,
  familyMvpEnabled: false,
  disabledTabs: [],
  tabs: {} as ConfigContextValue["tabs"],
  theme: "system",
  baseCurrency: "GBP",
  enableAdvancedAnalytics: true,
  dataQualityAdmin: true,
  refreshConfig: async () => {},
  setRelativeViewEnabled: () => {},
  setBaseCurrency: () => {},
};

function renderWithConfig(dataQualityAdmin: boolean) {
  return render(
    <configContext.Provider value={{ ...baseConfig, dataQualityAdmin }}>
      <DataQuality />
    </configContext.Provider>,
  );
}

const position = (ticker: string, exchange: string, overrides: Record<string, unknown> = {}) => ({
  ticker,
  exchange,
  total_points: 100,
  first_date: "2026-01-01",
  last_date: "2026-06-01",
  gap_count: 0,
  gaps: [],
  duplicate_dates: [],
  outliers: [],
  ...overrides,
});

const issue = (overrides: Record<string, unknown>) => ({
  id: "WRONG_EXCHANGE:demo:isa:MICC.L",
  type: "WRONG_EXCHANGE",
  severity: "high",
  entity: { owner: "demo", account: "isa", holding: "MICC.L" },
  description: "Holding MICC.L has no metadata on L.",
  suggested_fix: "Correct holding exchange to MICC.N.",
  preview: { before: { ticker: "MICC.L" }, after: { ticker: "MICC.N" } },
  fixable: true,
  ...overrides,
});

beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  vi.clearAllMocks();
});

describe("DataQuality page (read-only fallback)", () => {
  it("renders a row per position with counts and RAG status", async () => {
    mockGetDataQualityTimeseries.mockResolvedValue({
      count: 3,
      positions: [
        position("CLEAN", "L"),
        position("GAPPY", "L", { gap_count: 1, gaps: [{ start: "2026-02-01", end: "2026-02-05", missing_business_days: 4 }] }),
        position("DUPED", "N", { duplicate_dates: ["2026-03-01"], outliers: [{ date: "2026-04-01", value: 999, z_score: 5.2 }] }),
      ],
    });

    renderWithConfig(false);

    expect(await screen.findByText("CLEAN")).toBeInTheDocument();
    expect(screen.getByText("GAPPY")).toBeInTheDocument();
    expect(screen.getByText("DUPED")).toBeInTheDocument();
    // Admin tabs are hidden in the read-only fallback.
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  });

  it("shows an empty state when no positions are cached", async () => {
    mockGetDataQualityTimeseries.mockResolvedValue({ count: 0, positions: [] });

    renderWithConfig(false);

    expect(await screen.findByText(en.dataQuality.noData)).toBeInTheDocument();
  });

  it("shows an error message when the request fails", async () => {
    mockGetDataQualityTimeseries.mockRejectedValueOnce(new Error("boom"));

    renderWithConfig(false);

    expect(await screen.findByText("boom")).toBeInTheDocument();
  });

  it("opens the drill-down modal with problematic dates for a position", async () => {
    mockGetDataQualityTimeseries.mockResolvedValue({
      count: 1,
      positions: [
        position("DUPED", "N", {
          gap_count: 1,
          gaps: [{ start: "2026-02-01", end: "2026-02-05", missing_business_days: 4 }],
          duplicate_dates: ["2026-03-01"],
          outliers: [{ date: "2026-04-01", value: 999, z_score: 5.2 }],
        }),
      ],
    });

    renderWithConfig(false);

    const viewDetailsButton = await screen.findByRole("button", {
      name: en.dataQuality.viewDetailsFor
        .replace("{{ticker}}", "DUPED")
        .replace("{{exchange}}", "N"),
    });
    await act(async () => {
      await userEvent.click(viewDetailsButton);
    });

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("2026-03-01");
    expect(dialog).toHaveTextContent("2026-04-01");
    expect(dialog).toHaveTextContent("2026-02-01");

    const closeButton = screen.getByRole("button", { name: en.dataQuality.drilldown.close });
    await act(async () => {
      await userEvent.click(closeButton);
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("does not emit duplicate-key warnings for same-ticker/different-exchange rows (#6505)", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    mockGetDataQualityTimeseries.mockResolvedValue({
      count: 4,
      positions: [
        {
          ticker: "CASH",
          exchange: "GBP",
          total_points: 100,
          first_date: "2026-01-01",
          last_date: "2026-06-01",
          gap_count: 0,
          gaps: [],
          duplicate_dates: [],
          outliers: [],
        },
        {
          ticker: "CASH",
          exchange: "L",
          total_points: 90,
          first_date: "2026-01-01",
          last_date: "2026-06-01",
          gap_count: 0,
          gaps: [],
          duplicate_dates: [],
          outliers: [],
        },
        {
          ticker: "PFE",
          exchange: "N",
          total_points: 80,
          first_date: "2026-01-01",
          last_date: "2026-06-01",
          gap_count: 0,
          gaps: [],
          duplicate_dates: [],
          outliers: [],
        },
        {
          ticker: "PFE",
          exchange: "L",
          total_points: 70,
          first_date: "2026-01-01",
          last_date: "2026-06-01",
          gap_count: 0,
          gaps: [],
          duplicate_dates: [],
          outliers: [],
        },
      ],
    });

    renderWithConfig(false);

    expect((await screen.findAllByText("CASH")).length).toBeGreaterThan(1);
    expect((await screen.findAllByText("PFE")).length).toBeGreaterThan(1);
    const keyWarnings = errorSpy.mock.calls.filter((args) =>
      String(args[0]).includes("same key"),
    );
    expect(keyWarnings).toEqual([]);
    errorSpy.mockRestore();
  });
});

describe("DataQuality admin UI", () => {
  it("shows the Issues tab by default with issue rows", async () => {
    mockGetDataQualityIssues.mockResolvedValue({
      count: 1,
      issues: [issue({})],
    });

    renderWithConfig(true);

    expect(await screen.findAllByText(/MICC\.L/)).not.toHaveLength(0);
    expect(screen.getAllByText("WRONG_EXCHANGE").length).toBeGreaterThan(0);
    expect(screen.getByText("Correct holding exchange to MICC.N.")).toBeInTheDocument();
    // Tab labels visible.
    expect(screen.getByRole("tab", { name: en.dataQuality.admin.tabs.issues })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: en.dataQuality.admin.tabs.audit })).toBeInTheDocument();
  });

  it("filters issues by type and ticker", async () => {
    mockGetDataQualityIssues.mockResolvedValue({
      count: 2,
      issues: [
        issue({ id: "WRONG_EXCHANGE:demo:isa:MICC.L", type: "WRONG_EXCHANGE", entity: { holding: "MICC.L" } }),
        issue({
          id: "GAPS:ABC:L",
          type: "GAPS",
          severity: "medium",
          entity: { ticker: "ABC", exchange: "L" },
          description: "1 gap(s) in ABC.L.",
          suggested_fix: "Refetch / fill the missing range.",
          preview: { before: { gap_count: 1 }, after: { gap_count: 0 } },
        }),
      ],
    });

    renderWithConfig(true);

    expect(await screen.findAllByText(/MICC\.L/)).not.toHaveLength(0);
    expect(screen.getByText(/^ABC\.L$/)).toBeInTheDocument();

    // Filter by type.
    await act(async () => {
      await userEvent.selectOptions(screen.getByLabelText(en.dataQuality.admin.issues.filters.type), "GAPS");
    });
    expect(screen.queryByText(/MICC\.L/)).not.toBeInTheDocument();
    expect(screen.getByText(/^ABC\.L$/)).toBeInTheDocument();

    // Reset and filter by ticker.
    await act(async () => {
      await userEvent.selectOptions(screen.getByLabelText(en.dataQuality.admin.issues.filters.type), "");
      await userEvent.type(screen.getByLabelText(en.dataQuality.admin.issues.filters.ticker), "ABC");
    });
    expect(screen.queryByText(/MICC\.L/)).not.toBeInTheDocument();
    expect(screen.getByText(/^ABC\.L$/)).toBeInTheDocument();
  });

  it("shows preview before/after and applies a fix", async () => {
    mockGetDataQualityIssues.mockResolvedValue({
      count: 1,
      issues: [issue({})],
    });
    mockFixDataQualityIssue.mockResolvedValue({ status: "fixed", ticker: "MICC.N", audit_id: "a1" });

    renderWithConfig(true);

    const previewButton = await screen.findByRole("button", {
      name: en.dataQuality.admin.issues.actions.previewFor.replace("{{entity}}", "demo / isa / MICC.L"),
    });
    await act(async () => {
      await userEvent.click(previewButton);
    });

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("MICC.L");
    expect(dialog).toHaveTextContent("MICC.N");

    // Apply from the preview dialog.
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: en.dataQuality.admin.issues.actions.apply }));
    });

    // Confirmation dialog then applies.
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: en.dataQuality.admin.issues.actions.apply }));
    });

    expect(mockFixDataQualityIssue).toHaveBeenCalledWith("WRONG_EXCHANGE:demo:isa:MICC.L");
    expect(await screen.findByText(en.dataQuality.admin.issues.actions.applied)).toBeInTheDocument();
  });

  it("applies fixes to all visible issues via batch", async () => {
    mockGetDataQualityIssues.mockResolvedValue({
      count: 2,
      issues: [
        issue({ id: "WRONG_EXCHANGE:demo:isa:MICC.L" }),
        issue({
          id: "WRONG_EXCHANGE:demo:isa:PFE.N",
          entity: { holding: "PFE.N" },
          preview: { before: { ticker: "PFE.N" }, after: { ticker: "PFE.N" } },
          suggested_fix: "Correct holding exchange to PFE.N.",
        }),
      ],
    });
    mockFixDataQualityBatch.mockResolvedValue({
      applied: 2,
      failed: 0,
      results: [
        { issue_id: "WRONG_EXCHANGE:demo:isa:MICC.L", status: "ok" },
        { issue_id: "WRONG_EXCHANGE:demo:isa:PFE.N", status: "ok" },
      ],
    });

    renderWithConfig(true);

    const fixAll = await screen.findByRole("button", {
      name: en.dataQuality.admin.issues.actions.fixAll,
    });
    await act(async () => {
      await userEvent.click(fixAll);
    });

    expect(mockFixDataQualityBatch).toHaveBeenCalledWith([
      "WRONG_EXCHANGE:demo:isa:MICC.L",
      "WRONG_EXCHANGE:demo:isa:PFE.N",
    ]);
    expect(
      await screen.findByText(
        en.dataQuality.admin.issues.actions.batchApplied.replace("{{applied}}", "2").replace("{{total}}", "2"),
      ),
    ).toBeInTheDocument();
  });

  it("shows the Audit tab with undo", async () => {
    mockGetDataQualityIssues.mockResolvedValue({ count: 0, issues: [] });
    mockGetDataQualityAudit.mockResolvedValue({
      count: 1,
      entries: [
        {
          id: "e1",
          timestamp: "2026-08-01T10:00:00Z",
          action: "wrong_exchange",
          issue_id: "WRONG_EXCHANGE:demo:isa:MICC.L",
          entity: { owner: "demo", account: "isa", holding: "MICC.L" },
          before: { holdings: [{ ticker: "MICC.L" }] },
          after: { holdings: [{ ticker: "MICC.N" }] },
          actor: "user@example.com",
        },
      ],
    });
    mockUndoDataQualityAudit.mockResolvedValue({ status: "undone", entry_id: "e1" });

    renderWithConfig(true);

    await act(async () => {
      await userEvent.click(screen.getByRole("tab", { name: en.dataQuality.admin.tabs.audit }));
    });

    expect(await screen.findByText("wrong_exchange")).toBeInTheDocument();
    const undoButton = screen.getByRole("button", {
      name: en.dataQuality.admin.audit.actions.undoFor.replace("{{entity}}", "demo / isa / MICC.L"),
    });
    await act(async () => {
      await userEvent.click(undoButton);
    });
    expect(mockUndoDataQualityAudit).toHaveBeenCalledWith("e1");
    expect(await screen.findByText(en.dataQuality.admin.audit.actions.undone)).toBeInTheDocument();
  });

  it("shows the Series tab with dedupe inside the admin UI", async () => {
    mockGetDataQualityIssues.mockResolvedValue({ count: 0, issues: [] });
    mockGetDataQualityTimeseries.mockResolvedValue({
      count: 1,
      positions: [position("DUPED", "N", { duplicate_dates: ["2026-03-01"] })],
    });
    mockDedupeDataQualitySeries.mockResolvedValue({ status: "fixed", removed: 1, rows: 2 });

    renderWithConfig(true);

    await act(async () => {
      await userEvent.click(screen.getByRole("tab", { name: en.dataQuality.admin.tabs.series }));
    });

    expect(await screen.findByText("DUPED")).toBeInTheDocument();
    const dedupeButton = screen.getByRole("button", {
      name: en.dataQuality.admin.series.dedupeFor.replace("{{ticker}}", "DUPED").replace("{{exchange}}", "N"),
    });
    await act(async () => {
      await userEvent.click(dedupeButton);
    });
    expect(mockDedupeDataQualitySeries).toHaveBeenCalledWith("DUPED", "N");
  });

  it("closes the preview dialog on Escape and returns focus to the trigger", async () => {
    mockGetDataQualityIssues.mockResolvedValue({
      count: 1,
      issues: [issue({})],
    });

    renderWithConfig(true);

    const previewButton = await screen.findByRole("button", {
      name: en.dataQuality.admin.issues.actions.previewFor.replace("{{entity}}", "demo / isa / MICC.L"),
    });
    await act(async () => {
      await userEvent.click(previewButton);
    });

    expect(await screen.findByRole("dialog")).toBeInTheDocument();

    await act(async () => {
      await userEvent.keyboard("{Escape}");
    });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(previewButton).toHaveFocus();
  });

  it("traps Tab focus within the confirm dialog", async () => {
    mockGetDataQualityIssues.mockResolvedValue({
      count: 1,
      issues: [issue({})],
    });

    renderWithConfig(true);

    const fixButton = await screen.findByRole("button", {
      name: en.dataQuality.admin.issues.actions.fixFor.replace("{{entity}}", "demo / isa / MICC.L"),
    });
    await act(async () => {
      await userEvent.click(fixButton);
    });

    const dialog = await screen.findByRole("dialog");
    const cancelButton = screen.getByRole("button", { name: en.dataQuality.admin.issues.actions.cancel });
    const applyButton = screen.getByRole("button", { name: en.dataQuality.admin.issues.actions.apply });

    expect(cancelButton).toHaveFocus();

    await act(async () => {
      await userEvent.tab({ shift: true });
    });
    expect(applyButton).toHaveFocus();
    expect(dialog).toContainElement(document.activeElement as HTMLElement);

    await act(async () => {
      await userEvent.tab();
    });
    expect(cancelButton).toHaveFocus();
  });

  it("moves between tabs with arrow keys and wires up ARIA tab/tabpanel relationships", async () => {
    mockGetDataQualityIssues.mockResolvedValue({ count: 0, issues: [] });
    mockGetDataQualityTimeseries.mockResolvedValue({ count: 0, positions: [] });

    renderWithConfig(true);

    const issuesTab = await screen.findByRole("tab", { name: en.dataQuality.admin.tabs.issues });
    const seriesTab = screen.getByRole("tab", { name: en.dataQuality.admin.tabs.series });

    expect(issuesTab).toHaveAttribute("aria-controls");
    const panel = document.getElementById(issuesTab.getAttribute("aria-controls")!);
    expect(panel).toHaveAttribute("role", "tabpanel");
    expect(panel).toHaveAttribute("aria-labelledby", issuesTab.id);

    issuesTab.focus();
    expect(issuesTab).toHaveFocus();

    await act(async () => {
      await userEvent.keyboard("{ArrowRight}");
    });
    expect(seriesTab).toHaveFocus();
    expect(seriesTab).toHaveAttribute("aria-selected", "true");
    expect(issuesTab).toHaveAttribute("aria-selected", "false");

    await act(async () => {
      await userEvent.keyboard("{ArrowLeft}");
    });
    expect(issuesTab).toHaveFocus();
    expect(issuesTab).toHaveAttribute("aria-selected", "true");
  });
});
