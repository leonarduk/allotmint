import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { PortfolioView } from "@/components/PortfolioView";
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
                holdings: [],
            },
            {
                account_type: "SIPP",
                currency: "GBP",
                value_estimate_gbp: 14925,
                last_updated: "2025-07-15",
                holdings: [],
            },
        ],
    };

    it("renders account blocks", () => {
        render(<PortfolioView data={mockOwner}/>);

        // Match headings like "ISA (GBP)"
        const isaBlock = screen.getByText((_, el) => {
            if (!el) return false;
            const isHeading = el.tagName.toLowerCase() === "h2";
            const startsWithIsa = el.textContent?.trim().startsWith("ISA") ?? false;
            return isHeading && startsWithIsa;
        });

        expect(isaBlock).toBeInTheDocument();

        expect(screen.getByText(/SIPP.*GBP/)).toBeInTheDocument();

    });

    it("updates total when accounts are toggled", () => {
        render(<PortfolioView data={mockOwner}/>);

        const total = screen.getByText(/Approx Total:/);
        expect(total).toHaveTextContent("£14,925.00");

        const sippCheckbox = screen.getByRole("checkbox", {name: /sipp/i});
        fireEvent.click(sippCheckbox);

        expect(total).toHaveTextContent("£0.00");
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

    it("shows the CSV import form when accounts exist", () => {
        render(<PortfolioView data={mockOwner} />);

        expect(screen.getByText(/import csv/i)).toBeInTheDocument();
    });

    it("calls onPositionAdded when CsvImportForm triggers onImported", async () => {
        const { importHoldingsCsv } = await import("@/api");
        vi.mocked(importHoldingsCsv).mockResolvedValue({ path: "steve/ISA/import.csv" });
        const onPositionAdded = vi.fn();

        render(<PortfolioView data={mockOwner} onPositionAdded={onPositionAdded} />);

        fireEvent.change(screen.getByLabelText(/provider/i), {
            target: { value: "degiro" },
        });
        const file = new File(["ticker,qty\nAAPL,1"], "holdings.csv", { type: "text/csv" });
        fireEvent.change(screen.getByLabelText(/csv file/i), {
            target: { files: [file] },
        });

        fireEvent.click(screen.getByRole("button", { name: /^import$/i }));

        await waitFor(() => expect(onPositionAdded).toHaveBeenCalledTimes(1));
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
