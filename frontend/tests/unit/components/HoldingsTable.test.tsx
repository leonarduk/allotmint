import { render, screen, within, act, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import i18n from "@/i18n";
import { formatDateISO } from "@/lib/date";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
vi.mock("@/api", async () => {
    const actual = await vi.importActual<typeof import("@/api")>("@/api");
    return {
        ...actual,
        getInstrumentDetail: vi.fn(() => Promise.resolve({ mini: { 7: [], 30: [], 180: [] } })),
        getGroupPortfolio: vi.fn(),
        getGroupAlphaVsBenchmark: vi.fn(() => Promise.resolve({ alpha_vs_benchmark: 0 })),
        getGroupTrackingError: vi.fn(() => Promise.resolve({ tracking_error: 0 })),
        getGroupMaxDrawdown: vi.fn(() => Promise.resolve({ max_drawdown: 0 })),
        getGroupSectorContributions: vi.fn(() => Promise.resolve([])),
        getGroupRegionContributions: vi.fn(() => Promise.resolve([])),
        getGroupInstruments: vi.fn(() => Promise.resolve([])),
    };
});
vi.mock("@/components/TopMoversSummary", () => ({
    TopMoversSummary: () => <div data-testid="top-movers-summary" />,
}));
import { HoldingsTable } from "@/components/HoldingsTable";
import { __clearInstrumentHistoryCache } from "@/hooks/useInstrumentHistory";
import { InstrumentTable } from "@/components/InstrumentTable";
import { GroupPortfolioView } from "@/components/GroupPortfolioView";
import { configContext, type AppConfig } from "@/ConfigContext";
import { getGroupPortfolio, getInstrumentDetail } from "@/api";
import type { InstrumentSummary } from "@/types";
import type { RollupRow } from "@/lib/rollupAdapter";

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
import type { Holding } from "@/types";

describe("HoldingsTable", () => {
    beforeEach(() => {
        localStorage.clear();
    });
    const holdings: Holding[] = [
        {
            ticker: "AAA",
            name: "Alpha",
            currency: "GBP",
            instrument_type: "Equity",
            units: 5,
            price: 0,
            cost_basis_gbp: 100,
            market_value_gbp: 150,
            gain_gbp: 50,
            current_price_gbp: 30,
            latest_source: "Feed",
            acquired_date: "2024-01-01",
            last_price_date: "2024-01-01",
            days_held: 100,
            sell_eligible: true,
            days_until_eligible: 0,
        },
        {
            ticker: "XYZ",
            name: "Test Holding",
            currency: "USD",
            instrument_type: "Equity",
            units: 5,
            price: 0,
            cost_basis_gbp: 500,
            market_value_gbp: 0,
            gain_gbp: -25,
            acquired_date: "",
            days_held: 0,
            sell_eligible: false,
            days_until_eligible: 10,
            next_eligible_sell_date: "2024-07-20",
        },
        {
            ticker: "GBXH",
            name: "GBX Holding",
            currency: "GBX",
            instrument_type: "Equity",
            units: 1,
            price: 0,
            cost_basis_gbp: 10,
            market_value_gbp: 10,
            gain_gbp: 0,
            acquired_date: "2024-01-05",
            days_held: 50,
            sell_eligible: false,
            days_until_eligible: 5,
        },
        {
            ticker: "CADH",
            name: "CAD Holding",
            currency: "CAD",
            instrument_type: "Equity",
            units: 1,
            price: 0,
            cost_basis_gbp: 20,
            market_value_gbp: 20,
            gain_gbp: 0,
            acquired_date: "2024-02-01",
            days_held: 30,
            sell_eligible: false,
            days_until_eligible: 0,
        },
    ];

    const rollupRows: RollupRow[] = [
        {
            ticker: "ROLL-A",
            name: "Rollup Alpha",
            units: 10,
            cost_basis_gbp: 500,
            effective_cost_basis_gbp: 500,
            market_value_gbp: 600,
            gain_gbp: 100,
            gain_pct: 20,
            weight_pct: 60,
            lot_count: 3,
            owners: ["Alice"],
            accounts: ["isa"],
            grouping: "Growth",
            exchange: "L",
            change_7d_pct: 2,
            change_30d_pct: 5,
            acquired_date: null,
            days_held: null,
            sell_eligible: null,
            days_until_eligible: null,
            next_eligible_sell_date: null,
        },
        {
            ticker: "ROLL-Z",
            name: "Rollup Zeta",
            units: 5,
            cost_basis_gbp: 400,
            effective_cost_basis_gbp: 400,
            market_value_gbp: 400,
            gain_gbp: 0,
            gain_pct: 0,
            weight_pct: 40,
            lot_count: 2,
            owners: ["Bob"],
            accounts: ["sipp"],
            grouping: "Income",
            exchange: "L",
            change_7d_pct: 1,
            change_30d_pct: 3,
            acquired_date: null,
            days_held: null,
            sell_eligible: null,
            days_until_eligible: null,
            next_eligible_sell_date: null,
        },
    ];

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

    it("toggles relative view", async () => {
        renderWithConfig(<HoldingsTable holdings={holdings} />);
        await screen.findByText("AAA");
        expect(screen.getByRole('columnheader', { name: 'Units' })).toBeInTheDocument();
        const toggle = screen.getByLabelText('Relative view');
        await userEvent.click(toggle);
        expect(screen.queryByRole('columnheader', { name: 'Units' })).toBeNull();
        expect(screen.getByRole('columnheader', { name: /Gain %/ })).toBeInTheDocument();
    });

    it("prioritizes financial columns and localizes the trend range", async () => {
        renderWithConfig(<HoldingsTable holdings={holdings} />);

        const headerRows = await screen.findAllByRole("row");
        const headers = within(headerRows[1])
            .getAllByRole("columnheader")
            .map((header) => header.textContent);

        expect(headers.slice(0, 8)).toEqual([
            "Ticker ▲",
            "Name",
            "Units",
            "Mkt £",
            "Gain £",
            "Gain %",
            "Px £",
            "Cost £",
        ]);
        expect(screen.getByRole("columnheader", { name: "Trend (30d)" })).toBeInTheDocument();
    });

    it("renders shared group totals and expands grouped holdings", async () => {
        const groupedHoldings = holdings.map((holding) => ({
            ...holding,
            grouping: holding.ticker === "XYZ" ? "Technology" : "Income",
        }));

        renderWithConfig(
            <HoldingsTable holdings={groupedHoldings} groupingMode="group" />,
        );

        const incomeToggle = screen.getByRole("button", { name: "Toggle Income" });
        expect(incomeToggle).toHaveAttribute("aria-expanded", "false");
        const incomeRow = incomeToggle.closest("tr");
        expect(incomeRow).not.toBeNull();
        expect(within(incomeRow!).getByText("£180.00")).toBeInTheDocument();
        expect(within(incomeRow!).getByText("£50.00")).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "AAA" })).toBeNull();

        await userEvent.click(incomeToggle);

        expect(incomeToggle).toHaveAttribute("aria-expanded", "true");
        expect(screen.getByRole("button", { name: "AAA" })).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "XYZ" })).toBeNull();
    });

    it("keeps the existing flat rendering when groupingMode is omitted", async () => {
        renderWithConfig(<HoldingsTable holdings={holdings} />);

        expect(await screen.findByRole("button", { name: "AAA" })).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: /Toggle / })).toBeNull();
    });

    it("falls back to group mode when category mode is requested without definitions", async () => {
        const groupedHoldings = holdings.map((holding) => ({
            ...holding,
            grouping: holding.ticker === "XYZ" ? "Technology" : "Income",
        }));

        renderWithConfig(
            <HoldingsTable holdings={groupedHoldings} groupingMode="category" />,
        );

        // Falls back to 'group' mode → meaningful headers, not "Uncategorised"
        expect(
            await screen.findByRole("button", { name: "Toggle Income" }),
        ).toBeInTheDocument();
        expect(
            screen.getByRole("button", { name: "Toggle Technology" }),
        ).toBeInTheDocument();
    });

    it("uses category definitions when provided in category mode", async () => {
        const groupedHoldings = holdings.map((holding) => ({
            ...holding,
            grouping: holding.ticker === "XYZ" ? "tech" : "dividend",
        }));

        renderWithConfig(
            <HoldingsTable
                holdings={groupedHoldings}
                groupingMode="category"
                categoryDefinitions={[
                    {
                        id: "tech-group",
                        name: "tech",
                        category: "growth",
                        category_name: "Growth Assets",
                    },
                    {
                        id: "div-group",
                        name: "dividend",
                        category: "income",
                        category_name: "Income Assets",
                    },
                ]}
            />,
        );

        // Category resolution: "tech" → "Growth Assets", "dividend" → "Income Assets"
        expect(
            await screen.findByRole("button", { name: /Toggle Growth Assets/ }),
        ).toBeInTheDocument();
        expect(
            screen.getByRole("button", { name: /Toggle Income Assets/ }),
        ).toBeInTheDocument();
    });

    it("produces group totals matching InstrumentTable for equivalent data", async () => {
        const parityInstruments: InstrumentSummary[] = [
            {
                ticker: "P1",
                name: "Parity One",
                grouping: "Alpha",
                currency: "GBP",
                instrument_type: "Equity",
                units: 10,
                market_value_gbp: 500,
                gain_gbp: 100,
            },
            {
                ticker: "P2",
                name: "Parity Two",
                grouping: "Alpha",
                currency: "GBP",
                instrument_type: "Equity",
                units: 5,
                market_value_gbp: 500,
                gain_gbp: -50,
            },
            {
                ticker: "P3",
                name: "Parity Three",
                grouping: "Beta",
                currency: "GBP",
                instrument_type: "Equity",
                units: 3,
                market_value_gbp: 300,
                gain_gbp: 30,
            },
        ];

        const parityHoldings = parityInstruments.map((inst) => ({
            ticker: inst.ticker,
            name: inst.name,
            grouping: inst.grouping,
            currency: inst.currency ?? "GBP",
            instrument_type: inst.instrument_type ?? "Equity",
            units: inst.units,
            price: 0,
            cost_basis_gbp: inst.market_value_gbp - inst.gain_gbp,
            market_value_gbp: inst.market_value_gbp,
            gain_gbp: inst.gain_gbp,
            current_price_gbp: 100,
            latest_source: "Feed",
            acquired_date: "2024-01-01",
            last_price_date: "2024-01-01",
            days_held: 100,
            sell_eligible: true,
            days_until_eligible: 0,
        }));

        const { unmount } = renderWithConfig(
            <MemoryRouter>
                <InstrumentTable rows={parityInstruments} />
            </MemoryRouter>,
        );

        // Capture InstrumentTable group header totals
        await screen.findByRole("button", { name: /Toggle Alpha/i });
        const itAlphaRow = screen.getByRole("button", { name: /Toggle Alpha/i }).closest("tr")!;
        const itAlphaMarket = within(itAlphaRow).getByText("£1,000.00").textContent;
        const itAlphaGainCell = within(itAlphaRow).getByText(/£50\.00/);
        const itAlphaGain = itAlphaGainCell.textContent;
        const itBetaRow = screen.getByRole("button", { name: /Toggle Beta/i }).closest("tr")!;
        const itBetaMarket = within(itBetaRow).getByText("£300.00").textContent;

        unmount();

        renderWithConfig(
            <HoldingsTable holdings={parityHoldings} groupingMode="group" />,
        );

        await screen.findByRole("button", { name: "Toggle Alpha" });
        const htAlphaRow = screen.getByRole("button", { name: "Toggle Alpha" }).closest("tr")!;
        const htAlphaMarket = within(htAlphaRow).getByText("£1,000.00").textContent;
        const htAlphaGainCell = within(htAlphaRow).getByText(/£50\.00/);
        const htAlphaGain = htAlphaGainCell.textContent;
        // InstrumentTable annotates gain with ▲/▼ prefix (formatSignedMoney);
        // HoldingsTable does not. Strip prefix for fair comparison.
        const stripPrefix = (text: string | null) => (text ?? "").replace(/^[▲▼]/, "");
        const htBetaRow = screen.getByRole("button", { name: "Toggle Beta" }).closest("tr")!;
        const htBetaMarket = within(htBetaRow).getByText("£300.00").textContent;

        expect(htAlphaMarket).toBe(itAlphaMarket);
        expect(stripPrefix(htAlphaGain)).toBe(stripPrefix(itAlphaGain));
        expect(htBetaMarket).toBe(itBetaMarket);
    });

    it("renders — for growth stage and eligibility when data is null (rollup rows)", async () => {
        const rollupRows: RollupRow[] = [
            {
                ticker: "ROLL",
                name: "Rollup Co",
                units: 10,
                cost_basis_gbp: 500,
                effective_cost_basis_gbp: 500,
                market_value_gbp: 600,
                gain_gbp: 100,
                gain_pct: 20,
                weight_pct: 10,
                lot_count: 3,
                owners: ["Alice"],
                accounts: ["isa"],
                grouping: "Growth",
                exchange: "L",
                change_7d_pct: 2,
                change_30d_pct: 5,
                acquired_date: null,
                days_held: null,
                sell_eligible: null,
                days_until_eligible: null,
                next_eligible_sell_date: null,
            },
        ];

        renderWithConfig(
            <HoldingsTable holdings={rollupRows} groupingMode="group" />,
        );

        await screen.findByRole("button", { name: "Toggle Growth" });
        // Expand the group to see the row
        await userEvent.click(screen.getByRole("button", { name: "Toggle Growth" }));

        const row = screen.getByText("Rollup Co").closest("tr")!;
        // Stage and eligibility cells should show "—" for null rollup fields
        const cells = within(row).getAllByText("—");
        // days_held cell, stage cell, eligibility cell, and acquired_date cell
        expect(cells.length).toBeGreaterThanOrEqual(3);
    });

    it("keeps footer columns aligned with the header in relative view", async () => {
        const TestProviderRelative = ({ children }: { children: React.ReactNode }) => (
            <configContext.Provider
              value={{
                ...defaultConfig,
                relativeViewEnabled: true,
                setRelativeViewEnabled: () => {},
                refreshConfig: async () => {},
                setBaseCurrency: () => {},
              }}
            >
                {children}
            </configContext.Provider>
        );
        render(
            <TestProviderRelative>
                <HoldingsTable holdings={holdings} />
            </TestProviderRelative>,
        );

        const rows = await screen.findAllByRole("row");
        const headerColumnCount = within(rows[1]).getAllByRole("columnheader").length;

        const table = screen.getByRole("table");
        const footerRow = table.querySelector("tfoot tr") as HTMLTableRowElement;
        const footerColumnCount = Array.from(footerRow.children).reduce(
            (sum, cell) => sum + (Number(cell.getAttribute("colspan")) || 1),
            0,
        );

        expect(footerColumnCount).toBe(headerColumnCount);
    });

    it("renders one sparkline per holding", async () => {
        renderWithConfig(<HoldingsTable holdings={holdings} />);

        await screen.findByText("AAA");
        expect(screen.getAllByTestId(/^sparkline/)).toHaveLength(holdings.length);
    });

    it("marks only the row matching the selected ticker as selected", async () => {
        renderWithConfig(<HoldingsTable holdings={holdings} selectedTicker="XYZ" />);

        const selectedRow = (await screen.findByText("Test Holding")).closest("tr");
        const otherRow = screen.getByText("Alpha").closest("tr");

        expect(selectedRow).toHaveAttribute("aria-selected", "true");
        expect(otherRow).not.toHaveAttribute("aria-selected");
    });

    it("shows days to go if not eligible", async () => {
        render(<HoldingsTable holdings={holdings}/>);
        const row = (await screen.findByText("Test Holding")).closest("tr");
        const cell = within(row!).getByText("✗ 10");
        expect(cell).toBeInTheDocument();
        const expected = formatDateISO(new Date('2024-07-20'));
        expect(cell).toHaveAttribute('title', expected);
    });

    it("marks stale prices with an asterisk", async () => {
        const stale: Holding = {
            ticker: "STALE",
            name: "Stale Co",
            currency: "GBP",
            instrument_type: "Equity",
            units: 1,
            price: 0,
            cost_basis_gbp: 100,
            market_value_gbp: 100,
            gain_gbp: 0,
            current_price_gbp: 100,
            acquired_date: "2024-01-01",
            days_held: 10,
            sell_eligible: true,
            days_until_eligible: 0,
            last_price_date: "2024-01-01",
            last_price_time: "2024-01-01T09:00:00Z",
            is_stale: true,
        };
        render(<HoldingsTable holdings={[stale]} />);
        const star = await screen.findByTitle("2024-01-01T09:00:00Z");
        expect(star).toHaveTextContent("*");
        const price = star.parentElement?.querySelector(".text-gray");
        expect(price).toHaveClass("text-gray");
    });

    it("creates FX pair buttons for currency and skips GBX", async () => {
        const onSelect = vi.fn();
        render(<HoldingsTable holdings={holdings} onSelectInstrument={onSelect}/>);
        await screen.findByRole('button', { name: 'USD' });
        await userEvent.click(screen.getByRole('button', { name: 'USD' }));
        expect(onSelect).toHaveBeenCalledTimes(1);
        expect(onSelect).toHaveBeenCalledWith('USDGBP.FX', 'USD');
        expect(screen.queryByRole('button', { name: 'GBX' })).toBeNull();
        expect(screen.getByRole('button', { name: 'CAD' })).toBeInTheDocument();
    });

    it("selects the instrument when clicking the name cell or elsewhere in the row", async () => {
        const onSelect = vi.fn();
        render(<HoldingsTable holdings={holdings} onSelectInstrument={onSelect}/>);

        await userEvent.click(await screen.findByText("Alpha"));
        // Third arg is the instrument type wired through for the detail flyout (Refs #6874);
        // holdings[0] ("AAA" / "Alpha") declares instrument_type: "Equity".
        expect(onSelect).toHaveBeenCalledWith("AAA", "Alpha", "Equity");

        onSelect.mockClear();
        const row = (await screen.findByText("Alpha")).closest("tr");
        expect(row).not.toBeNull();
        await userEvent.click(row!);
        expect(onSelect).toHaveBeenCalledWith("AAA", "Alpha", "Equity");
    });

    it("sorts by ticker when header clicked", async () => {
        render(<HoldingsTable holdings={holdings}/>);
        await screen.findByText("AAA");
        // initially sorted ascending by ticker => AAA first
        let rows = screen.getAllByRole("row");
        expect(within(rows[2]).getByText("AAA")).toBeInTheDocument();

        await userEvent.click(screen.getByText(/^Ticker/));
        rows = screen.getAllByRole("row");
        expect(within(rows[2]).getByText("XYZ")).toBeInTheDocument();
    });

    it("filters by ticker", async () => {
        render(<HoldingsTable holdings={holdings}/>);
        const input = await screen.findByPlaceholderText("Ticker");
        await userEvent.type(input, "AA");
        expect(screen.getByText("AAA")).toBeInTheDocument();
        expect(screen.queryByText("XYZ")).toBeNull();
    });

    it("filters by eligibility", async () => {
        render(<HoldingsTable holdings={holdings}/>);
        const select = await screen.findByLabelText("Sell eligible");
        await userEvent.selectOptions(select, "true");
        expect(screen.getByText("AAA")).toBeInTheDocument();
        expect(screen.queryByText("Test Holding")).toBeNull();
    });

    it("suppresses lot-only eligibility controls without changing the column count in rollup mode", async () => {
        const { unmount } = renderWithConfig(<HoldingsTable holdings={holdings} />);
        const flatHeaderRows = await screen.findAllByRole("row");
        const flatColumnCount = within(flatHeaderRows[0]).getAllByRole("columnheader").length;
        unmount();

        renderWithConfig(<HoldingsTable holdings={rollupRows} rollupMode />);
        const rollupHeaderRows = await screen.findAllByRole("row");

        expect(within(rollupHeaderRows[0]).getAllByRole("columnheader")).toHaveLength(flatColumnCount);
        expect(screen.queryByLabelText("Sell eligible")).toBeNull();
        expect(screen.queryByRole("button", { name: "Sell-eligible" })).toBeNull();
    });

    it("ignores a leftover eligibility filter after switching to rollup mode", async () => {
        const { rerender } = renderWithConfig(<HoldingsTable holdings={holdings} />);
        await userEvent.selectOptions(await screen.findByLabelText("Sell eligible"), "true");
        expect(screen.queryByText("Test Holding")).toBeNull();

        rerender(
            <TestProvider>
                <HoldingsTable holdings={rollupRows} rollupMode />
            </TestProvider>,
        );

        expect(await screen.findByText("ROLL-A")).toBeInTheDocument();
        expect(screen.getByText("ROLL-Z")).toBeInTheDocument();
    });

    it("does not sort by days held in rollup mode", async () => {
        renderWithConfig(<HoldingsTable holdings={rollupRows} rollupMode />);
        await screen.findByText("ROLL-A");
        const daysHeldHeader = screen.getByRole("columnheader", { name: "Days Held" });
        const tickersBefore = screen.getAllByText(/^ROLL-/).map((cell) => cell.textContent);

        expect(daysHeldHeader.className).not.toContain("clickable");
        expect(daysHeldHeader).not.toHaveTextContent("▲");
        expect(daysHeldHeader).not.toHaveTextContent("▼");
        await userEvent.click(daysHeldHeader);

        expect(screen.getAllByText(/^ROLL-/).map((cell) => cell.textContent)).toEqual(tickersBefore);
    });

    it("shows last price date badge when available", async () => {
        render(<HoldingsTable holdings={holdings} />);
        const row = (await screen.findByText("AAA")).closest("tr");
        const badge = within(row!).getByTitle("2024-01-01");
        expect(badge).toBeInTheDocument();
    });

    it("allows toggling columns", async () => {
        render(<HoldingsTable holdings={holdings}/>);
        await screen.findByText("AAA");
        expect(screen.getByRole('columnheader', {name: 'Units'})).toBeInTheDocument();
        const checkbox = screen.getByLabelText("Units");
        await userEvent.click(checkbox);
        await waitFor(() =>
            expect(screen.queryByRole('columnheader', {name: 'Units'})).toBeNull(),
        );
    });

      it("does not show price metadata source in the price column", async () => {
          render(<HoldingsTable holdings={holdings}/>);
          await screen.findByText("AAA");
          expect(screen.queryByText(/Source: Feed/)).toBeNull();
      });

      it("applies sell-eligible quick filter", async () => {
        render(<HoldingsTable holdings={holdings} />);
        await screen.findByText('AAA');
        await userEvent.click(screen.getByRole('button', { name: 'Sell-eligible' }));
        expect(screen.getByLabelText('Sell eligible')).toHaveValue('true');
        expect(screen.getByText('AAA')).toBeInTheDocument();
        expect(screen.queryByText('Test Holding')).toBeNull();
    });

    it("applies gain percentage quick filter", async () => {
        render(<HoldingsTable holdings={holdings} />);
        const input = await screen.findByPlaceholderText('Min Gain %');
        await userEvent.type(input, '10');
        expect(screen.getByPlaceholderText('Gain %')).toHaveValue('10');
        expect(screen.getByText('AAA')).toBeInTheDocument();
        expect(screen.queryByText('XYZ')).toBeNull();
    });

      it("persists view preset selection", async () => {
          const mixedHoldings: Holding[] = [
              ...holdings,
            {
                ticker: 'BND1',
                name: 'Bond Holding',
                currency: 'GBP',
                instrument_type: 'Bond',
                units: 1,
                price: 0,
                cost_basis_gbp: 100,
                market_value_gbp: 100,
                gain_gbp: 0,
                acquired_date: '',
                days_held: 0,
                sell_eligible: false,
                days_until_eligible: 0,
            },
        ];
        const { unmount } = render(<HoldingsTable holdings={mixedHoldings} />);
        await screen.findByText('AAA');
        await userEvent.click(screen.getByRole('button', { name: 'Bond' }));
        expect(screen.getByText('BND1')).toBeInTheDocument();
        expect(screen.queryByText('AAA')).toBeNull();
        unmount();
        render(<HoldingsTable holdings={mixedHoldings} />);
        await screen.findByText('BND1');
        expect(screen.getByPlaceholderText('Type')).toHaveValue('Bond');
        expect(screen.getByText('BND1')).toBeInTheDocument();
          expect(screen.queryByText('AAA')).toBeNull();
      });

      it("derives translated view presets from the holdings", async () => {
          const mixedHoldings: Holding[] = [
              holdings[0],
              { ...holdings[0], ticker: "OTHER", instrument_type: "Other" },
              { ...holdings[0], ticker: "TRUST", instrument_type: "Investment Trust" },
              { ...holdings[0], ticker: "UNKNOWN", instrument_type: "Commodity" },
          ];

          render(<HoldingsTable holdings={mixedHoldings} />);

          expect(await screen.findByRole("button", { name: "Equity" })).toBeInTheDocument();
          expect(screen.getByRole("button", { name: "Other" })).toBeInTheDocument();
          expect(screen.getByRole("button", { name: "Investment Trust" })).toBeInTheDocument();
          expect(screen.getByRole("button", { name: "Commodity" })).toBeInTheDocument();
          expect(screen.queryByRole("button", { name: "Bond" })).toBeNull();
      });

      it("clears a persisted view preset that is absent from the holdings", async () => {
          localStorage.setItem("holdingsTableViewPreset", "Bond");
          render(<HoldingsTable holdings={holdings} />);

          expect(await screen.findByText("AAA")).toBeInTheDocument();
          await waitFor(() => expect(screen.getByPlaceholderText("Type")).toHaveValue(""));
          expect(localStorage.getItem("holdingsTableViewPreset")).toBe("");
      });

      it("shows controls and fallback when no rows match", async () => {
          localStorage.setItem("holdingsTableViewPreset", "Equity");
          render(<HoldingsTable holdings={holdings} />);
          expect(await screen.findByText('View:')).toBeInTheDocument();
          await userEvent.type(screen.getByPlaceholderText("Ticker"), "missing");
          expect(screen.getByText('No holdings match the current filters.')).toBeInTheDocument();
          expect(screen.getByRole('button', { name: 'Clear filters' })).toBeInTheDocument();
          expect(screen.getByRole('button', { name: 'Open Screener' })).toBeInTheDocument();
          await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
          expect(screen.getByText('AAA')).toBeInTheDocument();
      });

      it("renders the group portfolio view without altering search params", async () => {
        const portfolio = {
          name: "At a glance",
          accounts: [
            {
              owner: "alice",
              account_type: "isa",
              holdings: [
                {
                  ticker: "AAA",
                  name: "Alpha",
                  currency: "GBP",
                  instrument_type: "Equity",
                  units: 1,
                  cost_basis_gbp: 100,
                  market_value_gbp: 150,
                  gain_gbp: 50,
                },
              ],
            },
          ],
        };
        vi.mocked(getGroupPortfolio).mockResolvedValue(portfolio as any);
        vi.stubGlobal(
          "ResponsiveContainer",
          ({ children }: any) => <div>{children}</div>,
        );
        vi.stubGlobal("LineChart", ({ children }: any) => <div>{children}</div>);
        vi.stubGlobal("Line", () => <div />);
        vi.stubGlobal("XAxis", () => <div />);
        vi.stubGlobal("YAxis", () => <div />);
        vi.stubGlobal("Tooltip", () => <div />);
        renderWithConfig(
          <MemoryRouter>
            <GroupPortfolioView
              slug="all"
              owners={[{ owner: "alice", full_name: "Alice Example", accounts: ["isa"] }]}
            />
          </MemoryRouter>,
        );
        expect(await screen.findByText("At a glance")).toBeInTheDocument();
        expect(window.location.search).toBe("");
        vi.unstubAllGlobals();
      });

      it("renders translated text in Spanish", async () => {
          await act(async () => {
              await i18n.changeLanguage('es');
          });
          render(<HoldingsTable holdings={holdings} />);
          expect(await screen.findByText('Vista:')).toBeInTheDocument();
          expect(screen.getByRole('button', { name: 'Todos' })).toBeInTheDocument();
          await act(async () => {
              await i18n.changeLanguage('en');
          });
      });

      it("renders rows and keeps header on scroll", async () => {
          vi.useFakeTimers();
          try {
              const manyHoldings = Array.from({ length: 50 }, (_, i) => ({
                  ...holdings[0],
                  ticker: `T${i}`,
                  name: `Name${i}`,
              }));
              render(<HoldingsTable holdings={manyHoldings} />);
              expect(screen.getByRole('columnheader', { name: 'Ticker' })).toBeInTheDocument();
              const container = screen.getByRole('table').parentElement as HTMLElement;
              act(() => {
                  container.scrollTop = 500;
                  container.dispatchEvent(new Event('scroll'));
              });
              // Flush the @tanstack/virtual-core debounce timer so it fires before
              // JSDOM teardown (avoids "window is not defined" unhandled error).
              act(() => { vi.runAllTimers(); });
              expect(screen.getByRole('columnheader', { name: 'Ticker' })).toBeInTheDocument();
          } finally {
              vi.useRealTimers();
          }
      });

      it("shows an accessible top scrollbar for overflowing holdings columns", () => {
          const clientWidth = vi.spyOn(HTMLElement.prototype, "clientWidth", "get");
          const scrollWidth = vi.spyOn(HTMLElement.prototype, "scrollWidth", "get");
          clientWidth.mockReturnValue(600);
          scrollWidth.mockReturnValue(1200);

          render(<HoldingsTable holdings={holdings} />);
          const tableContainer = screen.getByRole('table').parentElement as HTMLElement;
          const topScrollbar = screen.getByRole('region', {
              name: 'Scroll holdings columns horizontally',
          });

          expect(topScrollbar).toHaveAttribute("tabindex", "0");
          expect(topScrollbar).toHaveAttribute("aria-hidden", "false");
          expect(topScrollbar.firstElementChild).toHaveStyle({ width: "1200px" });

          topScrollbar.scrollLeft = 240;
          fireEvent.scroll(topScrollbar);
          expect(tableContainer.scrollLeft).toBe(240);

          tableContainer.scrollLeft = 80;
          fireEvent.scroll(tableContainer);
          expect(topScrollbar.scrollLeft).toBe(80);

          clientWidth.mockRestore();
          scrollWidth.mockRestore();
      });

      it("shows a consolidated notice when some holdings have no price history", async () => {
          __clearInstrumentHistoryCache();
          vi.mocked(getInstrumentDetail).mockResolvedValue({
              prices: [],
              mini: { 7: [], 30: [], 180: [] },
              positions: [],
          });
          // This file's async vi.mock factory does not intercept the hook's API
          // import (Vitest module-graph quirk), so the preload runs through the
          // real api layer; stub fetch so it resolves to an empty-history
          // payload. Either path yields the same notice.
          vi.stubGlobal(
              "fetch",
              vi.fn(() =>
                  Promise.resolve({
                      ok: true,
                      json: async () => ({
                          prices: [],
                          mini: { 7: [], 30: [], 180: [] },
                          positions: [],
                      }),
                  } as Response),
              ),
          );
          renderWithConfig(<HoldingsTable holdings={holdings} />);

          // Rendering the notice proves the full wiring: HoldingsTable preloads
          // the held tickers, resolves empty history, and counts them once.
          expect(
              await screen.findByText("4 instruments have no price history"),
          ).toBeInTheDocument();
          expect(screen.getAllByText(/no price history/i)).toHaveLength(1);
          vi.unstubAllGlobals();
      });
  });
