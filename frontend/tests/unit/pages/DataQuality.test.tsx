import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
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
const mockGetDataStewardLatest = vi.hoisted(() => vi.fn());
const mockRunBotNow = vi.hoisted(() => vi.fn());
const mockGetBotRun = vi.hoisted(() => vi.fn());

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
    getDataStewardLatest: mockGetDataStewardLatest,
    runBotNow: mockRunBotNow,
    getBotRun: mockGetBotRun,
  };
});

const baseConfig: ConfigContextValue = {
  configLoaded: true,
  relativeViewEnabled: false,
  familyMvpEnabled: false,
  disabledTabs: [],
  tabs: {} as ConfigContextValue["tabs"],
  theme: "system",
  reportingCurrency: "GBP",
  enableAdvancedAnalytics: true,
  dataQualityAdmin: true,
  refreshConfig: async () => {},
  setRelativeViewEnabled: () => {},
};

function renderWithConfig(dataQualityAdmin: boolean) {
  return render(
    <MemoryRouter>
      <configContext.Provider value={{ ...baseConfig, dataQualityAdmin }}>
        <DataQuality />
      </configContext.Provider>
    </MemoryRouter>,
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

  it("links issue entities to the instrument research page", async () => {
    mockGetDataQualityIssues.mockResolvedValue({
      count: 2,
      issues: [
        issue({ id: "GAPS:ABC:L", type: "GAPS", entity: { ticker: "ABC", exchange: "L" } }),
        issue({ id: "X:cash", type: "GAPS", entity: { ticker: "EURGBP=X" } }),
      ],
    });

    renderWithConfig(true);

    const link = await screen.findByRole("link", { name: "ABC.L" });
    expect(link).toHaveAttribute("href", "/research/ABC.L");
    // Symbols with no research page render as plain text.
    expect(screen.queryByRole("link", { name: /EURGBP/ })).toBeNull();
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
    mockGetDataStewardLatest.mockResolvedValue(null);

    renderWithConfig(true);

    const issuesTab = await screen.findByRole("tab", { name: en.dataQuality.admin.tabs.issues });
    // The steward report tab sits right after Issues (#10471).
    const stewardTab = screen.getByRole("tab", { name: en.dataQuality.admin.tabs.steward });

    expect(issuesTab).toHaveAttribute("aria-controls");
    const panel = document.getElementById(issuesTab.getAttribute("aria-controls")!);
    expect(panel).toHaveAttribute("role", "tabpanel");
    expect(panel).toHaveAttribute("aria-labelledby", issuesTab.id);

    issuesTab.focus();
    expect(issuesTab).toHaveFocus();

    await act(async () => {
      await userEvent.keyboard("{ArrowRight}");
    });
    expect(stewardTab).toHaveFocus();
    expect(stewardTab).toHaveAttribute("aria-selected", "true");
    expect(issuesTab).toHaveAttribute("aria-selected", "false");

    await act(async () => {
      await userEvent.keyboard("{ArrowLeft}");
    });
    expect(issuesTab).toHaveFocus();
    expect(issuesTab).toHaveAttribute("aria-selected", "true");
  });
});

const stewardReport = (overrides: Record<string, unknown> = {}) => ({
  run_id: "run-1",
  started_at: "2026-10-09T02:00:00Z",
  finished_at: "2026-10-09T02:03:00Z",
  status: "ok",
  provider: "ollama",
  model: "qwen3.5:9b",
  totals: { input_tokens: 1200, output_tokens: 300, tool_calls: 3, cost_usd: 0 },
  portfolio_value_gbp: 10000,
  issues_found: 4,
  issues_held: 2,
  issues_investigated: 2,
  skipped_unheld: 2,
  skipped_over_limit: 0,
  errors: [],
  items: [
    {
      issue_id: "STALE_SERIES:VWRL:L",
      issue_type: "STALE_SERIES",
      severity: "medium",
      entity: { ticker: "VWRL", exchange: "L" },
      description: "VWRL.L is 20 days stale.",
      fixable: true,
      verdict: "fix_available",
      root_cause: "source_outage",
      summary: "No prices since 19 Sep.",
      confidence: 0.9,
      exposure_gbp: 7000,
      exposure_pct: 70,
      evidence: [
        {
          tool: "get_data_freshness",
          arguments: { ticker: "VWRL.L" },
          result: '{"last_date": "2026-09-19"}',
          truncated: false,
          is_error: false,
        },
      ],
      proposed_fix: {
        method: "POST",
        path: "/data-quality/issues/STALE_SERIES%3AVWRL%3AL/fix",
        issue_id: "STALE_SERIES:VWRL:L",
        description: "Refetch the series.",
      },
    },
    {
      issue_id: "OUTLIERS:JEGI:L",
      issue_type: "OUTLIERS",
      severity: "low",
      entity: { ticker: "JEGI", exchange: "L" },
      description: "JEGI.L outliers.",
      fixable: false,
      verdict: "needs_human",
      root_cause: "epoch_zero_row+unadjusted_split",
      summary: "A 1969-12-31 row and an unrecorded split.",
      unclear: ["split ratio"],
      confidence: 0.8,
      exposure_gbp: 2500,
      exposure_pct: 25,
      evidence: [],
    },
  ],
  ...overrides,
});

async function openStewardTab() {
  mockGetDataQualityIssues.mockResolvedValue({ count: 0, issues: [] });
  renderWithConfig(true);
  const tab = await screen.findByRole("tab", { name: en.dataQuality.admin.tabs.steward });
  await act(async () => {
    await userEvent.click(tab);
  });
}

describe("DataQuality steward report (#10471)", () => {
  it("groups the latest report by verdict with exposure, cause and evidence", async () => {
    mockGetDataStewardLatest.mockResolvedValue(stewardReport());
    await openStewardTab();

    const fixGroup = await screen.findByRole("region", { name: en.dataQuality.admin.steward.groups.fix_available });
    expect(fixGroup).toHaveTextContent("VWRL.L");
    expect(fixGroup).toHaveTextContent("£7,000");
    expect(fixGroup).toHaveTextContent("source_outage");
    expect(fixGroup).toHaveTextContent("get_data_freshness");

    const humanGroup = screen.getByRole("region", { name: en.dataQuality.admin.steward.groups.needs_human });
    expect(humanGroup).toHaveTextContent("epoch_zero_row+unadjusted_split");
    expect(humanGroup).toHaveTextContent("split ratio");
    // Only fix-available items offer Apply.
    expect(screen.getAllByRole("button", { name: /Apply fix for/ })).toHaveLength(1);
  });

  it("applies a proposed fix through the existing fix endpoint after confirmation", async () => {
    mockGetDataStewardLatest.mockResolvedValue(stewardReport());
    mockFixDataQualityIssue.mockResolvedValue({ status: "fixed", audit_id: "a1" });
    await openStewardTab();

    await userEvent.click(await screen.findByRole("button", { name: "Apply fix for VWRL.L" }));
    expect(mockFixDataQualityIssue).not.toHaveBeenCalled();
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Refetch the series.");
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: en.dataQuality.admin.issues.actions.apply }));
    });

    expect(mockFixDataQualityIssue).toHaveBeenCalledWith("STALE_SERIES:VWRL:L");
    expect(await screen.findByRole("status")).toHaveTextContent(en.dataQuality.admin.issues.actions.applied);
    // The applied item is marked, not offered again.
    expect(screen.getByText(en.dataQuality.admin.steward.applied)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Apply fix for VWRL.L" })).not.toBeInTheDocument();
  });

  it("shows an empty state before the first run and runs the bot on demand", async () => {
    mockGetDataStewardLatest
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce(stewardReport({ items: [], issues_investigated: 0 }));
    mockRunBotNow.mockResolvedValue({ id: "run-9", bot_id: "data-steward", status: "ok" });
    await openStewardTab();

    expect(await screen.findByText(en.dataQuality.admin.steward.empty)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: en.dataQuality.admin.steward.botsLink })).toHaveAttribute("href", "/bots");
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: en.dataQuality.admin.steward.runNow }));
    });
    expect(mockRunBotNow).toHaveBeenCalledWith("data-steward");
    expect(await screen.findByText(en.dataQuality.admin.steward.noItems)).toBeInTheDocument();
  });

  it("polls a background bot run until it finishes, then shows its report", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      mockGetDataStewardLatest.mockResolvedValueOnce(null).mockResolvedValueOnce(stewardReport());
      mockRunBotNow.mockResolvedValue({ id: "run-9", bot_id: "data-steward", status: "running" });
      mockGetBotRun.mockResolvedValue({ id: "run-9", bot_id: "data-steward", status: "ok" });
      await openStewardTab();

      await act(async () => {
        await userEvent.click(await screen.findByRole("button", { name: en.dataQuality.admin.steward.runNow }));
        await vi.advanceTimersByTimeAsync(3000);
      });
      expect(mockGetBotRun).toHaveBeenCalledWith("data-steward", "run-9");
      expect(
        await screen.findByRole("region", { name: en.dataQuality.admin.steward.groups.fix_available }),
      ).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows why a bot run failed", async () => {
    mockGetDataStewardLatest.mockResolvedValue(null);
    mockRunBotNow.mockResolvedValue({
      id: "run-9",
      bot_id: "data-steward",
      status: "failed",
      error: "setup: MCP_SERVER_URL is not set",
    });
    await openStewardTab();

    await act(async () => {
      await userEvent.click(await screen.findByRole("button", { name: en.dataQuality.admin.steward.runNow }));
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("MCP_SERVER_URL is not set");
  });

  it("shows run errors from the report", async () => {
    mockGetDataStewardLatest.mockResolvedValue(
      stewardReport({ status: "error", items: [], errors: [{ stage: "setup", error: "MCP_SERVER_URL is not set" }] }),
    );
    await openStewardTab();

    expect(await screen.findByRole("list", { name: en.dataQuality.admin.steward.runErrors })).toHaveTextContent(
      "setup: MCP_SERVER_URL is not set",
    );
  });
});
