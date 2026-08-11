import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { PortfolioView } from "@/components/PortfolioView";
import { aggregateHoldingsByTicker } from "@/utils/aggregateHoldings";
import type { Portfolio } from "@/types";
import { configContext } from "@/ConfigContext";

vi.mock("@/api", () => ({
  complianceForOwner: vi.fn().mockResolvedValue({ warnings: [] }),
  getOwnerSectorContributions: vi.fn().mockResolvedValue([]),
  getValueAtRisk: vi.fn().mockResolvedValue({ var: { "1d": 0, "10d": 0 } }),
  recomputeValueAtRisk: vi.fn().mockResolvedValue(undefined),
  getVarBreakdown: vi.fn().mockResolvedValue([]),
  createAccount: vi.fn(),
  importHoldingsCsv: vi.fn(),
  reconcileHoldingsCsv: vi.fn(),
}));

vi.mock("@/components/PerformanceDashboard", () => ({
  __esModule: true,
  default: () => <div data-testid="performance-dashboard" />,
}));

describe("PortfolioView", () => {
    const mockOwner: Portfolio = {
        owner: "steve",
        as_of: "2025-07-29",
        trades_this_month: 0,
        trades_remaining: 20,
        total_value_estimate_gbp: 14925,
        accounts: [
            {
                account_type: "ISA",
                currency: "GBP",
                value_estimate_gbp: 0,
                last_updated: "2025-07-24",
                holdings: [
                    { ticker: "SHARED", name: "Shared holding", units: 1, market_value_gbp: 10, cost_basis_gbp: 8, gain_gbp: 2, gain_pct: 25, day_change_gbp: 1 },
                ],
            },
            {
                account_type: "SIPP",
                currency: "GBP",
                value_estimate_gbp: 14925,
                last_updated: "2025-07-15",
                holdings: [
                    { ticker: "SHARED", name: "Shared holding", units: 2, market_value_gbp: 20, effective_cost_basis_gbp: 10, gain_gbp: 10, gain_pct: 100, day_change_gbp: 3 },
                ],
            },
        ],
    };

    it("sums day change and uses effective cost when aggregating account lots", () => {
        const [combined] = aggregateHoldingsByTicker(
            [
                { ticker: "SHARED", name: "Shared", units: 1, market_value_gbp: 10, cost_basis_gbp: 8, gain_gbp: 2, gain_pct: 25, day_change_gbp: 1, row_key: "isa-0" },
                { ticker: "SHARED", name: "Shared", units: 2, market_value_gbp: 20, effective_cost_basis_gbp: 10, gain_gbp: 10, gain_pct: 100, day_change_gbp: 3, row_key: "sipp-0" },
            ],
            "2025-07-29",
        );

        expect(combined).toMatchObject({
            market_value_gbp: 30,
            cost_basis_gbp: 18,
            gain_gbp: 12,
            gain_pct: 12 / 18 * 100,
            day_change_gbp: 4,
        });
    });

    it("combines matching tickers and recomputes totals in the all-accounts tab", () => {
        render(<PortfolioView data={mockOwner}/>);

        expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
            "All accounts",
            "ISA",
            "SIPP",
        ]);
        expect(screen.queryByRole("columnheader", { name: "Account" })).not.toBeInTheDocument();
        expect(screen.getAllByText("SHARED")).toHaveLength(1);
        const row = screen.getByText("SHARED").closest("tr")!;
        expect(within(row).getByText("3")).toBeInTheDocument();
        expect(within(row).getByText("£30.00")).toBeInTheDocument();
        expect(within(row).getByText("£12.00")).toBeInTheDocument();
        expect(within(row).getByText("66.7%")).toBeInTheDocument();
    });

    it("allows the holdings section to use the full portfolio width", () => {
        render(<PortfolioView data={mockOwner} />);

        const holdings = screen.getByRole("region", { name: "Portfolio holdings" });
        const layout = holdings.parentElement?.parentElement;

        expect(layout).toHaveClass("grid-cols-1");
        expect(layout?.className).not.toContain("xl:grid-cols-");
    });

    it("updates holdings and total when the active account tab changes", () => {
        render(<PortfolioView data={mockOwner}/>);

        const total = screen.getByText(/Approx Total:/);
        expect(total).toHaveTextContent("£14,925.00");

        fireEvent.click(screen.getByRole("tab", { name: "ISA" }));

        expect(total).toHaveTextContent("£0.00");
        expect(screen.getByText("Shared holding")).toBeInTheDocument();
        expect(screen.getAllByText("SHARED")).toHaveLength(1);
        expect(screen.queryByRole("columnheader", { name: "Account" })).not.toBeInTheDocument();

        fireEvent.click(screen.getByRole("tab", { name: "SIPP" }));
        expect(total).toHaveTextContent("£14,925.00");
        expect(screen.getByText("Shared holding")).toBeInTheDocument();
        expect(screen.getAllByText("SHARED")).toHaveLength(1);
    });

    it("resets the active account tab to 'all' when the owner changes even if the new owner has a colliding account key", () => {
        const otherOwner: Portfolio = {
            owner: "jane",
            as_of: "2025-07-29",
            trades_this_month: 0,
            trades_remaining: 20,
            total_value_estimate_gbp: 500,
            accounts: [
                {
                    account_type: "ISA",
                    currency: "GBP",
                    value_estimate_gbp: 500,
                    last_updated: "2025-07-24",
                    holdings: [
                        { ticker: "OTHER", name: "Jane ISA holding", units: 1, market_value_gbp: 500 },
                    ],
                },
            ],
        };

        const { rerender } = render(<PortfolioView data={mockOwner} />);
        fireEvent.click(screen.getByRole("tab", { name: "ISA" }));
        expect(screen.getByRole("tab", { name: "ISA" })).toHaveAttribute("aria-selected", "true");

        rerender(<PortfolioView data={otherOwner} />);

        expect(screen.getByRole("tab", { name: "All accounts" })).toHaveAttribute("aria-selected", "true");
        const total = screen.getByText(/Approx Total:/);
        expect(total).toHaveTextContent("£500.00");
    });

    it("preserves table filter state while switching account tabs", () => {
        render(<PortfolioView data={mockOwner} />);

        const tickerFilter = screen.getAllByPlaceholderText("Ticker")[0];
        fireEvent.change(tickerFilter, { target: { value: "SHAR" } });
        fireEvent.click(screen.getByRole("tab", { name: "ISA" }));

        expect(screen.getAllByPlaceholderText("Ticker")[0]).toHaveValue("SHAR");
    });

    it("shows an 'Add account' button for an owner with accounts", () => {
        render(<PortfolioView data={mockOwner} />);

        expect(screen.getByRole("button", { name: /add account/i })).toBeInTheDocument();
    });

    it("opens the add-account form when 'Add account' is clicked", () => {
        render(<PortfolioView data={mockOwner} />);

        fireEvent.click(screen.getByRole("button", { name: /add account/i }));

        expect(screen.getByLabelText(/account type/i)).toBeInTheDocument();
    });

    it("shows a guided empty state when the owner has no accounts", () => {
        const emptyOwner: Portfolio = { ...mockOwner, accounts: [] };

        render(<PortfolioView data={emptyOwner} />);

        expect(screen.getByText(/get started/i)).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: /add account/i }));

        expect(screen.getByLabelText(/account type/i)).toBeInTheDocument();
    });

    it("shows an accessible skeleton while the portfolio is loading", () => {
        render(<PortfolioView data={null} loading />);

        expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
        expect(screen.queryByText(/Approx Total:/)).not.toBeInTheDocument();
    });

    it("renders the portfolio dashboard once loading completes", () => {
        render(<PortfolioView data={mockOwner} loading={false} />);

        expect(screen.getByText(/Approx Total:/)).toBeInTheDocument();
    });

    it("shows an accessible skeleton while sector data is loading", async () => {
        const { getOwnerSectorContributions } = await import("@/api");
        vi.mocked(getOwnerSectorContributions).mockReturnValue(new Promise(() => {}));

        render(<PortfolioView data={mockOwner} />);

        expect(await screen.findByRole("status", { name: /loading/i })).toBeInTheDocument();
    });

    it("shows the CSV import form when 'Import CSV' is clicked for an owner with accounts", () => {
        render(<PortfolioView data={mockOwner} />);

        expect(screen.queryByLabelText(/provider/i)).not.toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: /\+ import csv/i }));

        expect(screen.getByLabelText(/provider/i)).toBeInTheDocument();
    });

    it("calls onPositionAdded when CsvImportForm triggers onImported", async () => {
        const { importHoldingsCsv } = await import("@/api");
        vi.mocked(importHoldingsCsv).mockResolvedValue({ path: "steve/ISA/import.csv" });
        const onPositionAdded = vi.fn();

        render(<PortfolioView data={mockOwner} onPositionAdded={onPositionAdded} />);
        fireEvent.click(screen.getByRole("button", { name: /\+ import csv/i }));

        fireEvent.change(screen.getByLabelText(/provider/i), {
            target: { value: "hargreaves" },
        });
        const file = new File(["ticker,qty\nAAPL,1"], "holdings.csv", { type: "text/csv" });
        fireEvent.change(screen.getByLabelText(/csv file/i), {
            target: { files: [file] },
        });

        fireEvent.click(screen.getByRole("button", { name: /^import$/i }));

        await waitFor(() => expect(onPositionAdded).toHaveBeenCalledTimes(1));
    });

    it("preserves the active account when the add-position form is collapsed and reopened", () => {
        Element.prototype.scrollIntoView = vi.fn();
        render(<PortfolioView data={mockOwner} />);

        fireEvent.click(screen.getByRole("tab", { name: "SIPP" }));
        fireEvent.click(screen.getByRole("button", { name: /\+ add position/i }));
        const addPositionForm = screen.getByRole("form", { name: /^add position$/i });
        expect(within(addPositionForm).getByLabelText(/account/i)).toHaveValue("SIPP");

        fireEvent.click(screen.getByRole("button", { name: /collapse add position form/i }));
        fireEvent.click(screen.getByRole("button", { name: /\+ add position/i }));

        expect(within(screen.getByRole("form", { name: /^add position$/i })).getByLabelText(/account/i)).toHaveValue("SIPP");
    });

    it("collapses the add-position form on Escape and ignores other keys", () => {
        render(<PortfolioView data={mockOwner} />);
        const addButton = screen.getByRole("button", { name: /\+ add position/i });
        expect(addButton).toHaveAttribute("aria-expanded", "false");

        fireEvent.click(addButton);
        expect(screen.getByRole("button", { name: /collapse add position form/i })).toHaveAttribute(
            "aria-expanded",
            "true",
        );

        fireEvent.keyDown(document, { key: "Enter" });
        expect(screen.getByRole("form", { name: /^add position$/i })).toBeInTheDocument();

        fireEvent.keyDown(document, { key: "Escape" });
        expect(screen.queryByRole("form", { name: /^add position$/i })).not.toBeInTheDocument();

        fireEvent.keyDown(document, { key: "Escape" });
        expect(screen.getByRole("button", { name: /\+ add position/i })).toBeInTheDocument();
    });

    it("hides the CSV import form when no accounts exist", () => {
        const emptyOwner: Portfolio = { ...mockOwner, accounts: [] };

        render(<PortfolioView data={emptyOwner} />);

        expect(screen.queryByText(/import csv/i)).not.toBeInTheDocument();
    });

    it("shows the CSV import form when accounts exist regardless of familyMvpEnabled", () => {
        render(
            <configContext.Provider
                value={{
                    relativeViewEnabled: false,
                    tabs: {
                        group: true,
                        market: true,
                        owner: true,
                        instrument: true,
                        performance: true,
                        transactions: true,
                        screener: true,
                        trading: true,
                        timeseries: true,
                        watchlist: true,
                        allocation: true,
                        rebalance: true,
                        movers: true,
                        instrumentadmin: true,
                        dataadmin: true,
                        virtual: true,
                        research: true,
                        support: true,
                        settings: true,
                        profile: false,
                        alerts: true,
                        pension: true,
                        trail: false,
                        alertsettings: true,
                        taxtools: false,
                        "trade-compliance": false,
                        reports: false,
                        scenario: false,
                    },
                    theme: "system",
                    baseCurrency: "GBP",
                    enableAdvancedAnalytics: true,
                    familyMvpEnabled: true,
                    disabledTabs: [],
                    refreshConfig: async () => {},
                    setRelativeViewEnabled: () => {},
                    setBaseCurrency: () => {},
                }}
            >
                <PortfolioView data={mockOwner} />
            </configContext.Provider>,
        );

        fireEvent.click(screen.getByRole("button", { name: /\+ import csv/i }));

        expect(screen.getByText(/import csv/i)).toBeInTheDocument();
    });

    it("hides advanced analytics panels when feature flag is disabled", () => {
        render(
            <configContext.Provider
                value={{
                    relativeViewEnabled: false,
                    tabs: {
                        group: true,
                        market: true,
                        owner: true,
                        instrument: true,
                        performance: true,
                        transactions: true,
                        screener: true,
                        trading: true,
                        timeseries: true,
                        watchlist: true,
                        allocation: true,
                        rebalance: true,
                        movers: true,
                        instrumentadmin: true,
                        dataadmin: true,
                        virtual: true,
                        research: true,
                        support: true,
                        settings: true,
                        profile: false,
                        alerts: true,
                        pension: true,
                        trail: false,
                        alertsettings: true,
                        taxtools: false,
                        "trade-compliance": false,
                        reports: false,
                        scenario: false,
                    },
                    theme: "system",
                    baseCurrency: "GBP",
                    enableAdvancedAnalytics: false,
                    disabledTabs: [],
                    refreshConfig: async () => {},
                    setRelativeViewEnabled: () => {},
                    setBaseCurrency: () => {},
                }}
            >
                <PortfolioView data={mockOwner} />
            </configContext.Provider>,
        );

        expect(screen.queryByText(/Sector contribution/i)).not.toBeInTheDocument();
        expect(screen.queryByTestId("performance-dashboard")).not.toBeInTheDocument();
    });
});
