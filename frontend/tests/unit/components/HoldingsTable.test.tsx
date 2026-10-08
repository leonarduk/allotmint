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
import { COLUMN_VISIBILITY_STORAGE_KEY, DETAILED_COLUMNS } from "@/lib/holdingsColumns";
import { __clearInstrumentHistoryCache } from "@/hooks/useInstrumentHistory";
import { InstrumentTable } from "@/components/InstrumentTable";
import { GroupPortfolioView } from "@/components/GroupPortfolioView";
import { configContext, type AppConfig } from "@/ConfigContext";
import { getGroupPortfolio, getInstrumentDetail } from "@/api";
import type { InstrumentSummary } from "@/types";
import type { RollupRow } from "@/lib/rollupAdapter";
import tableStyles from "@/styles/table.module.css";

const defaultConfig: AppConfig = {
    relativeViewEnabled: false,
    theme: "system",
    reportingCurrency: "GBP",
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
        // Start from Detailed: every column on, which is exactly the layout
        // these tests were written against (before #7832 the six toggleable
        // columns defaulted on and the other ten were always rendered). The
        // "column presets" tests below cover the Simple default.
        localStorage.setItem(
            COLUMN_VISIBILITY_STORAGE_KEY,
            JSON.stringify(DETAILED_COLUMNS),
        );
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
        const headers = within(headerRows[0])
            .getAllByRole("columnheader")
            .map((header) => header.textContent);

        expect(headers.slice(0, 11)).toEqual([
            "Ticker ▲",
            "Name",
            "Sector",
            "Units",
            "Mkt £",
            "Gain £",
            "Gain %",
            "Total return £",
            "Income £",
            "Px £",
            "Cost £",
        ]);
        expect(screen.getByRole("columnheader", { name: "Trend (30d)" })).toBeInTheDocument();
    });

    it("shows total return with its income breakdown, and N/A when unknown (#9038)", async () => {
        const withReturns = [
            { ...holdings[0], income_gbp: 20, realised_gain_gbp: 40, total_return_gbp: 90, total_return_pct: 18 },
            { ...holdings[1], income_gbp: 5, realised_gain_gbp: null, total_return_gbp: null, total_return_pct: null },
        ];
        renderWithConfig(<HoldingsTable holdings={withReturns} />);

        const known = (await screen.findByText(withReturns[0].name)).closest("tr")!;
        const knownCell = within(known).getByText(/\(18\.0%\)/);
        expect(knownCell.textContent).toMatch(/90\.00/);
        expect(knownCell.getAttribute("title")).toMatch(/20\.00/);

        const unknown = screen.getByText(withReturns[1].name).closest("tr")!;
        expect(within(unknown).getAllByText("N/A").length).toBeGreaterThan(0);
        // Any unknown position withholds the footer total rather than understating it.
        const footer = screen.getByText("Total").closest("tr")!;
        expect(within(footer).queryByText(/90\.00/)).toBeNull();
    });

    it("sorts by total return when its header is clicked", async () => {
        const rows = [
            { ...holdings[0], total_return_gbp: 10, total_return_pct: 2 },
            { ...holdings[1], total_return_gbp: 90, total_return_pct: 18 },
        ];
        renderWithConfig(<HoldingsTable holdings={rows} />);
        await screen.findByText(rows[0].name);

        const header = screen.getByRole("columnheader", { name: /^Total return/ });
        await userEvent.click(header);
        let bodyRows = screen.getAllByRole("row");
        expect(within(bodyRows[1]).getByText(rows[0].name)).toBeInTheDocument();
        expect(header.textContent).toMatch(/▲$/);

        await userEvent.click(header);
        bodyRows = screen.getAllByRole("row");
        expect(within(bodyRows[1]).getByText(rows[1].name)).toBeInTheDocument();
        expect(header.textContent).toMatch(/▼$/);
    });

    it("shows the total return and its income breakdown on rollup rows (#10395)", async () => {
        const rows: RollupRow[] = [
            { ...rollupRows[0], income_gbp: 30, realised_gain_gbp: 5, total_return_gbp: 135, total_return_pct: 27 },
        ];
        renderWithConfig(<HoldingsTable holdings={rows} rollupMode />);

        const row = (await screen.findByText(rows[0].name)).closest("tr")!;
        const cell = within(row).getByText(/\(27\.0%\)/);
        expect(cell.textContent).toMatch(/135\.00/);
        expect(cell.getAttribute("title")).toMatch(/30\.00/);
    });

    it("shows income per position with its yield, marks estimates, and totals it (#10395)", async () => {
        const rows = [
            { ...holdings[0], income_gbp: 20.5, income_estimated: false, yield_pct: 4.25, total_return_gbp: 90 },
            { ...holdings[1], income_gbp: 5, income_estimated: true, yield_pct: null, total_return_gbp: 10 },
        ];
        renderWithConfig(<HoldingsTable holdings={rows} />);

        const recorded = (await screen.findByText(rows[0].name)).closest("tr")!;
        const recordedCell = within(recorded).getByTitle("Trailing 12-month yield 4.3%");
        expect(recordedCell.textContent).toBe("£20.50");

        const estimated = screen.getByText(rows[1].name).closest("tr")!;
        const estimatedCell = within(estimated).getByText("≈£5.00");
        expect(estimatedCell.getAttribute("title")).toMatch(/^Estimated from dividend history/);

        const footer = screen.getByText("Total").closest("tr")!;
        expect(within(footer).getByText("£25.50")).toBeInTheDocument();
    });

    it("withholds the income total when any position's income is unknown (#10395)", async () => {
        const rows = [
            { ...holdings[0], income_gbp: 20, total_return_gbp: 90 },
            { ...holdings[1], income_gbp: null, total_return_gbp: null },
        ];
        renderWithConfig(<HoldingsTable holdings={rows} />);

        const unknown = (await screen.findByText(rows[1].name)).closest("tr")!;
        expect(within(unknown).getAllByText("N/A").length).toBeGreaterThan(0);
        const footer = screen.getByText("Total").closest("tr")!;
        expect(within(footer).queryByText("£20.00")).toBeNull();
    });

    it("shows a total return without a % when the % is unknown (#9038)", async () => {
        const rows = [{ ...holdings[0], income_gbp: 0, realised_gain_gbp: 0, total_return_gbp: 12, total_return_pct: null }];
        renderWithConfig(<HoldingsTable holdings={rows} />);

        const row = (await screen.findByText(rows[0].name)).closest("tr")!;
        const cell = within(row).getAllByText(/12\.00/)[0];
        expect(cell.textContent).not.toMatch(/\(/);
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

    it("renders the group count with the theme-aware groupCount class (#8532)", () => {
        const groupedHoldings = holdings.map((holding) => ({
            ...holding,
            grouping: holding.ticker === "XYZ" ? "Technology" : "Income",
        }));

        renderWithConfig(
            <HoldingsTable holdings={groupedHoldings} groupingMode="group" />,
        );

        const technologyToggle = screen.getByRole("button", { name: "Toggle Technology" });
        expect(within(technologyToggle).getByText("(1)")).toHaveClass(tableStyles.groupCount);
    });

    it("keeps the existing flat rendering when groupingMode is omitted", async () => {
        renderWithConfig(<HoldingsTable holdings={holdings} />);

        expect(await screen.findByRole("button", { name: "AAA" })).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: /Toggle / })).toBeNull();
    });

    it("keeps each expanded group's rows under its own header and sorts groups by totals (#8529)", async () => {
        // Ticker order interleaves the sectors: AAA(Tech), BBB(Energy), CCC(Tech), DDD(Energy).
        const make = (ticker: string, sector: string, market: number, gain: number): Holding => ({
            ...holdings[0],
            ticker,
            name: `${ticker} plc`,
            sector,
            cost_basis_gbp: market - gain,
            market_value_gbp: market,
            gain_gbp: gain,
        });
        const sectorHoldings = [
            make("AAA", "Tech", 100, 50),
            make("BBB", "Energy", 50, 10),
            make("CCC", "Tech", 100, 50),
            make("DDD", "Energy", 400, 10),
        ];

        const { container } = renderWithConfig(
            <HoldingsTable holdings={sectorHoldings} groupingMode="sector" />,
        );
        const bodyOrder = () =>
            Array.from(container.querySelectorAll("tbody tr")).map((row) => {
                const button = row.querySelector("button");
                return button?.getAttribute("aria-label") ?? button?.textContent;
            });

        // Collapsed groups render only their header rows, none of their holdings.
        expect(bodyOrder()).toEqual(["Toggle Energy", "Toggle Tech"]);

        // Expanding one group shows only that group's rows, under its header.
        await userEvent.click(screen.getByRole("button", { name: "Toggle Tech" }));
        expect(bodyOrder()).toEqual(["Toggle Energy", "Toggle Tech", "AAA", "CCC"]);
        await userEvent.click(screen.getByRole("button", { name: "Toggle Energy" }));

        // Ticker ▲ sorts groups by label; rows stay contiguous under their header.
        expect(bodyOrder()).toEqual(["Toggle Energy", "BBB", "DDD", "Toggle Tech", "AAA", "CCC"]);

        // Weight % ▲: Tech (£200) before Energy (£450).
        await userEvent.click(screen.getByRole("columnheader", { name: /Weight %/ }));
        expect(bodyOrder()).toEqual(["Toggle Tech", "AAA", "CCC", "Toggle Energy", "BBB", "DDD"]);

        // Gain £ ▲ then ▼: Energy (£20) / Tech (£100) by group gain total.
        await userEvent.click(screen.getByRole("columnheader", { name: /Gain £/ }));
        expect(bodyOrder()).toEqual(["Toggle Energy", "BBB", "DDD", "Toggle Tech", "AAA", "CCC"]);
        await userEvent.click(screen.getByRole("columnheader", { name: /Gain £/ }));
        expect(bodyOrder()).toEqual(["Toggle Tech", "AAA", "CCC", "Toggle Energy", "BBB", "DDD"]);

        // Cost £ ▲ then ▼: Tech (£50 + £50 = £100) / Energy (£40 + £390 = £430) by summed cost.
        await userEvent.click(screen.getByRole("columnheader", { name: /Cost £/ }));
        expect(bodyOrder()).toEqual(["Toggle Tech", "AAA", "CCC", "Toggle Energy", "BBB", "DDD"]);
        await userEvent.click(screen.getByRole("columnheader", { name: /Cost £/ }));
        // Rows within a group follow the flat sort too: DDD (£390) before BBB (£40).
        expect(bodyOrder()).toEqual(["Toggle Energy", "DDD", "BBB", "Toggle Tech", "AAA", "CCC"]);

        // Gain % ▲ then ▼ by group gain %: Energy (£20 / £430 ≈ 4.7%) / Tech (£100 / £100 = 100%).
        // Within Energy, rows follow the flat sort: DDD (≈2.6%) before BBB (25%) when ascending.
        await userEvent.click(screen.getByRole("columnheader", { name: /Gain %/ }));
        expect(bodyOrder()).toEqual(["Toggle Energy", "DDD", "BBB", "Toggle Tech", "AAA", "CCC"]);
        await userEvent.click(screen.getByRole("columnheader", { name: /Gain %/ }));
        expect(bodyOrder()).toEqual(["Toggle Tech", "AAA", "CCC", "Toggle Energy", "BBB", "DDD"]);
    });

    it("sorts groups by label, not first-appearance order, for Ticker ▲/▼ (#8529)", async () => {
        // Label order (Alpha, Zulu) is the opposite of ticker order (AAA in Zulu, ZZZ in Alpha).
        const labelHoldings: Holding[] = [
            { ...holdings[0], ticker: "ZZZ", name: "Zed plc", sector: "Alpha" },
            { ...holdings[0], ticker: "AAA", name: "Ay plc", sector: "Zulu" },
        ];
        const { container } = renderWithConfig(
            <HoldingsTable holdings={labelHoldings} groupingMode="sector" />,
        );
        const headerOrder = () =>
            Array.from(container.querySelectorAll("tbody tr button[aria-label]")).map((button) =>
                button.getAttribute("aria-label"),
            );

        expect(headerOrder()).toEqual(["Toggle Alpha", "Toggle Zulu"]);
        await userEvent.click(screen.getByRole("columnheader", { name: /Ticker/ }));
        expect(headerOrder()).toEqual(["Toggle Zulu", "Toggle Alpha"]);
    });

    it("sorts rows within each group by Days Held; groups follow their first row (#8529)", async () => {
        // Days held: Tech AAA 10, CCC 150; Energy BBB 200, DDD 50.
        const daysHoldings: Holding[] = [
            { ...holdings[0], ticker: "AAA", name: "AAA plc", sector: "Tech", days_held: 10 },
            { ...holdings[0], ticker: "BBB", name: "BBB plc", sector: "Energy", days_held: 200 },
            { ...holdings[0], ticker: "CCC", name: "CCC plc", sector: "Tech", days_held: 150 },
            { ...holdings[0], ticker: "DDD", name: "DDD plc", sector: "Energy", days_held: 50 },
        ];
        const { container } = renderWithConfig(
            <HoldingsTable holdings={daysHoldings} groupingMode="sector" />,
        );
        const bodyOrder = () =>
            Array.from(container.querySelectorAll("tbody tr")).map((row) => {
                const button = row.querySelector("button");
                return button?.getAttribute("aria-label") ?? button?.textContent;
            });
        await userEvent.click(screen.getByRole("button", { name: "Toggle Tech" }));
        await userEvent.click(screen.getByRole("button", { name: "Toggle Energy" }));

        const daysHeldHeader = screen.getByRole("columnheader", { name: /Days Held/ });
        expect(daysHeldHeader.className).toContain("clickable");

        // ▲: AAA(10) leads, so Tech comes first; Energy rows DDD(50) then BBB(200).
        await userEvent.click(daysHeldHeader);
        expect(daysHeldHeader).toHaveTextContent("▲");
        expect(bodyOrder()).toEqual(["Toggle Tech", "AAA", "CCC", "Toggle Energy", "DDD", "BBB"]);

        // ▼: BBB(200) leads, so Energy comes first; Tech rows CCC(150) then AAA(10).
        await userEvent.click(daysHeldHeader);
        expect(daysHeldHeader).toHaveTextContent("▼");
        expect(bodyOrder()).toEqual(["Toggle Energy", "BBB", "DDD", "Toggle Tech", "CCC", "AAA"]);
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

        // Rows still render under the fallback grouping once expanded (#8529).
        await userEvent.click(screen.getByRole("button", { name: "Toggle Technology" }));
        expect(screen.getByRole("button", { name: "XYZ" })).toBeInTheDocument();
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

    it("renders an explicit N/A state (not a bare —) for acquired/days-held/stage/eligibility when data is null (rollup rows)", async () => {
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

        // acquired_date, days_held, stage, and eligibility all render an explicit,
        // distinctly-styled "N/A" instead.
        const naCells = within(row).getAllByText("N/A");
        expect(naCells.length).toBe(4);
        naCells.forEach((cell) => {
            expect(cell.className).toContain("notApplicable");
        });

        // Each N/A carries a tooltip explaining why the data is missing, so it
        // reads as "genuinely no data" rather than a loading/bug state.
        expect(
            screen.getByTitle("No acquisition date recorded"),
        ).toBeInTheDocument();
        expect(screen.getByTitle("Days held not available")).toBeInTheDocument();
        expect(screen.getByTitle("Growth stage unavailable")).toBeInTheDocument();
        expect(
            within(row).getByTitle("Sell eligibility not available"),
        ).toBeInTheDocument();
    });

    it("still renders real acquired/days-held/stage/eligibility data normally (no N/A)", async () => {
        renderWithConfig(<HoldingsTable holdings={holdings} />);

        const row = (await screen.findByText("Alpha")).closest("tr")!;
        expect(within(row).queryByText("N/A")).toBeNull();
        const acquiredCell = within(row)
            .getAllByText(formatDateISO(new Date("2024-01-01")))
            .find((el) => el.tagName === "TD");
        expect(acquiredCell).toBeInTheDocument();
        expect(within(row).getByText("100")).toBeInTheDocument();
        expect(within(row).getByText(/Eligible/)).toBeInTheDocument();
    });

    it("renders Gain £/Gain % as an explicit N/A (not a confident £0.00) when cost_basis_source is unknown (#7220 review follow-up)", async () => {
        // Regression guard: a holding with no booked cost and no acquisition
        // date has its cost set equal to market value as a last resort
        // (backend/common/holding_utils.py), so gain_gbp/gain_pct arrive as
        // real 0s -- but that 0 is a guess, not a fact. cost_basis_source is
        // tagged "unknown" for exactly this case so the UI can render an
        // honest N/A here instead of a misleading "you broke even".
        const unknownCostHolding: Holding = {
            ticker: "UNKC",
            name: "Unknown Cost Co",
            units: 5,
            acquired_date: null,
            price: 8,
            cost_basis_gbp: null,
            effective_cost_basis_gbp: 40,
            market_value_gbp: 40,
            gain_gbp: 0,
            gain_pct: 0,
            current_price_gbp: 8,
            cost_basis_source: "unknown",
        };

        renderWithConfig(<HoldingsTable holdings={[unknownCostHolding]} />);

        const row = (await screen.findByText("Unknown Cost Co")).closest("tr")!;
        const naCells = within(row).getAllByText("N/A");
        // Gain £ and Gain % both render N/A; other unrelated null fields on
        // this holding (acquired/days-held/stage/eligible) also render N/A,
        // so assert on the specific tooltips rather than an exact count.
        expect(naCells.length).toBeGreaterThanOrEqual(2);
        expect(within(row).getAllByTitle("Gain unknown — no acquisition date or booked cost on record").length).toBe(2);
        expect(
            within(row).getByTitle("No acquisition date or booked cost on record — cost assumed equal to current value"),
        ).toBeInTheDocument();
        // The cost cell still shows a real (non-N/A) number, equal to market
        // value (£40.00 appears for both Mkt £ and Cost £) -- it is the gain
        // that must be hidden, not the cost.
        expect(within(row).getAllByText("£40.00")).toHaveLength(2);
    });

    describe("unknown cost basis (#8471)", () => {
        const gainUnknownTitle =
            "Gain unknown — no acquisition date or booked cost on record";
        const zeroCostHolding: Holding = {
            ticker: "ZERO",
            name: "Zero Cost Co",
            units: 5,
            cost_basis_gbp: 0,
            effective_cost_basis_gbp: 0,
            market_value_gbp: 100,
            gain_gbp: null,
            gain_pct: null,
            current_price_gbp: 20,
        };
        const knownHolding: Holding = {
            ticker: "KNWN",
            name: "Known Cost Co",
            units: 1,
            cost_basis_gbp: 100,
            market_value_gbp: 150,
            gain_gbp: 50,
            gain_pct: 50,
            current_price_gbp: 150,
            cost_basis_source: "book",
        };
        const guessedCostHolding: Holding = {
            ticker: "GUESS",
            name: "Guessed Cost Co",
            units: 5,
            cost_basis_gbp: null,
            effective_cost_basis_gbp: 40,
            market_value_gbp: 40,
            gain_gbp: null,
            gain_pct: null,
            current_price_gbp: 8,
            cost_basis_source: "unknown",
        };

        it("renders N/A, not 0.0%, for gain % when cost is zero and gain_pct is null", async () => {
            renderWithConfig(<HoldingsTable holdings={[zeroCostHolding]} />);

            const row = (await screen.findByText("Zero Cost Co")).closest("tr")!;
            expect(within(row).getAllByTitle(gainUnknownTitle)).toHaveLength(2);
            expect(within(row).queryByText("0.0%")).toBeNull();
        });

        it("does not report the whole market value as gain when cost is zero (#7220)", async () => {
            // A legacy payload with gain_gbp == market value and no cost must
            // not be shown as a £100 gain.
            renderWithConfig(
                <HoldingsTable
                    holdings={[{ ...zeroCostHolding, gain_gbp: 100 }]}
                />,
            );

            const row = (await screen.findByText("Zero Cost Co")).closest("tr")!;
            expect(within(row).getAllByTitle(gainUnknownTitle)).toHaveLength(2);
            // £100.00 appears once, for market value only.
            expect(within(row).getAllByText("£100.00")).toHaveLength(1);
        });

        it("leaves unknown-gain rows out of the minimum gain filter", async () => {
            renderWithConfig(
                <HoldingsTable holdings={[knownHolding, zeroCostHolding]} />,
            );
            await screen.findByText("Zero Cost Co");

            await userEvent.type(screen.getByPlaceholderText("Min Gain %"), "-10");

            expect(screen.getByText("Known Cost Co")).toBeInTheDocument();
            expect(screen.queryByText("Zero Cost Co")).toBeNull();
        });

        it("weights the total gain % by known-cost rows only", async () => {
            renderWithConfig(
                <HoldingsTable holdings={[knownHolding, guessedCostHolding]} />,
            );
            await screen.findByText("Guessed Cost Co");

            const footer = screen.getByRole("table").querySelector("tfoot")!;
            // £50 gain on the £100 known cost; the £40 guessed cost must not
            // dilute it to 35.7%.
            expect(within(footer as HTMLElement).getByText("50.0%")).toBeInTheDocument();
            expect(within(footer as HTMLElement).queryByText("35.7%")).toBeNull();
        });

        it("keeps a booked-cost holding with a null gain_gbp in the cost totals and its booked label", async () => {
            // A real booked cost with a missing gain must not be treated as
            // unknown: its gain is derived (market - cost) and its cost stays
            // in both the footer and the group header totals.
            const bookedNullGain: Holding = {
                ticker: "BOOKN",
                name: "Booked Null Gain Co",
                units: 1,
                cost_basis_gbp: 100,
                market_value_gbp: 130,
                gain_gbp: null,
                gain_pct: null,
                current_price_gbp: 130,
                cost_basis_source: "book",
            };
            const other: Holding = {
                ...knownHolding,
                ticker: "OTHER",
                name: "Other Co",
                cost_basis_gbp: 50,
                market_value_gbp: 60,
                gain_gbp: 10,
                gain_pct: 20,
            };

            const { unmount } = renderWithConfig(
                <HoldingsTable holdings={[bookedNullGain, other]} />,
            );
            const row = (await screen.findByText("Booked Null Gain Co")).closest("tr")!;
            expect(within(row).queryByTitle(gainUnknownTitle)).toBeNull();
            expect(within(row).getByTitle("Actual purchase cost")).toBeInTheDocument();
            expect(within(row).getByText("£30.00")).toBeInTheDocument();
            const footer = screen.getByRole("table").querySelector("tfoot") as HTMLElement;
            expect(within(footer).getByText("£150.00")).toBeInTheDocument();
            expect(within(footer).getByText("£40.00")).toBeInTheDocument();
            unmount();

            renderWithConfig(
                <HoldingsTable
                    holdings={[
                        { ...bookedNullGain, grouping: "Mixed" },
                        { ...other, grouping: "Mixed" },
                    ] as Holding[]}
                    groupingMode="group"
                />,
            );
            const groupRow = (
                await screen.findByRole("button", { name: "Toggle Mixed" })
            ).closest("tr")!;
            expect(within(groupRow).getByText("£150.00")).toBeInTheDocument();
            expect(within(groupRow).getByText("£40.00")).toBeInTheDocument();
        });

        it("shows N/A, not £0.00, for gain and cost of an all-unreliable-cost group (#8531)", async () => {
            renderWithConfig(
                <HoldingsTable
                    holdings={[
                        { ...guessedCostHolding, grouping: "Unreliable" },
                        { ...knownHolding, grouping: "Reliable" },
                    ] as Holding[]}
                    groupingMode="group"
                />,
            );
            const unreliableRow = (
                await screen.findByRole("button", { name: "Toggle Unreliable" })
            ).closest("tr")!;
            expect(within(unreliableRow).getAllByText("N/A")).toHaveLength(2);
            // Both N/A spans (Gain £ and Cost £) explain why via the tooltip.
            expect(within(unreliableRow).getAllByTitle(gainUnknownTitle)).toHaveLength(2);
            expect(within(unreliableRow).queryByText("£0.00")).toBeNull();
            expect(within(unreliableRow).getByText("£40.00")).toBeInTheDocument();

            const reliableRow = screen
                .getByRole("button", { name: "Toggle Reliable" })
                .closest("tr")!;
            expect(within(reliableRow).queryByText("N/A")).toBeNull();
            expect(within(reliableRow).getByText("£50.00")).toBeInTheDocument();
            expect(within(reliableRow).getByText("£100.00")).toBeInTheDocument();
        });

        it("shows — for units in a multi-instrument group header but sums a single-ticker group (#8531)", async () => {
            renderWithConfig(
                <HoldingsTable
                    holdings={[
                        { ...knownHolding, units: 7, grouping: "Mixed" },
                        { ...knownHolding, ticker: "OTHER", name: "Other Co", units: 3, grouping: "Mixed" },
                        { ...knownHolding, ticker: "SOLO", name: "Solo A", units: 4, grouping: "Solo", acquired_date: "2020-01-01" },
                        { ...knownHolding, ticker: "SOLO", name: "Solo B", units: 6, grouping: "Solo", acquired_date: "2021-01-01" },
                    ] as Holding[]}
                    groupingMode="group"
                />,
            );
            const mixedRow = (
                await screen.findByRole("button", { name: "Toggle Mixed" })
            ).closest("tr")!;
            // The first <td> after the group label <th> is the Units cell.
            expect(within(mixedRow).getAllByRole("cell")[0]).toHaveTextContent(/^—$/);

            const soloRow = screen
                .getByRole("button", { name: "Toggle Solo" })
                .closest("tr")!;
            expect(within(soloRow).getAllByRole("cell")[0]).toHaveTextContent(/^10$/);
        });

        it("keeps the computed gain for a holding with a real cost", async () => {
            renderWithConfig(<HoldingsTable holdings={[knownHolding]} />);

            const row = (await screen.findByText("Known Cost Co")).closest("tr")!;
            expect(within(row).queryByTitle(gainUnknownTitle)).toBeNull();
            expect(within(row).getByText("£50.00")).toBeInTheDocument();
            expect(within(row).getByText("50.0%")).toBeInTheDocument();
        });
    });

    it("renders Gain £/Gain % as N/A, not a re-derived +12,679%, when cost_basis_source is book_suspect (#8472)", async () => {
        // The backend nulls gain_gbp/gain_pct for an implausible booked cost;
        // the table must not fall back to market - cost and resurrect the
        // absurd gain it withheld.
        const suspectHolding: Holding = {
            ticker: "AV.L",
            name: "Aviva",
            units: 50,
            acquired_date: null,
            price: 672.4,
            cost_basis_gbp: 263,
            effective_cost_basis_gbp: 263,
            market_value_gbp: 33620,
            gain_gbp: null,
            gain_pct: null,
            current_price_gbp: 672.4,
            cost_basis_source: "book_suspect",
        };

        renderWithConfig(<HoldingsTable holdings={[suspectHolding]} />);

        const row = (await screen.findByText("Aviva")).closest("tr")!;
        const tip = "Book cost looks implausible against the price — gain hidden until it is checked";
        // Gain £, Gain % and the Cost £ cell all carry the explanation.
        expect(within(row).getAllByTitle(tip).length).toBe(3);
        expect(within(row).queryByText(/12,6\d\d/)).not.toBeInTheDocument();
        expect(within(row).getByText("£263.00")).toBeInTheDocument();
    });

    it("keeps book_suspect rows out of the footer gain and total gain % (#8472)", async () => {
        const plausible: Holding = {
            ticker: "OK.L",
            name: "Plausible Co",
            units: 10,
            acquired_date: null,
            price: 10,
            cost_basis_gbp: 80,
            effective_cost_basis_gbp: 80,
            market_value_gbp: 100,
            gain_gbp: 20,
            gain_pct: 25,
            current_price_gbp: 10,
            cost_basis_source: "book",
        };
        const suspect: Holding = {
            ticker: "AV.L",
            name: "Aviva",
            units: 50,
            acquired_date: null,
            price: 672.4,
            cost_basis_gbp: 263,
            effective_cost_basis_gbp: 263,
            market_value_gbp: 33620,
            gain_gbp: null,
            gain_pct: null,
            current_price_gbp: 672.4,
            cost_basis_source: "book_suspect",
        };

        const { container } = renderWithConfig(<HoldingsTable holdings={[plausible, suspect]} />);
        await screen.findByText("Aviva");

        const footer = container.querySelector("tfoot")!;
        // Only the plausible holding's £20 / 25% counts toward the totals.
        expect(within(footer).getByText("£20.00")).toBeInTheDocument();
        expect(within(footer).getByText("25.0%")).toBeInTheDocument();
    });

    it("keeps footer columns aligned with the header in relative view", async () => {
        const TestProviderRelative = ({ children }: { children: React.ReactNode }) => (
            <configContext.Provider
              value={{
                ...defaultConfig,
                relativeViewEnabled: true,
                setRelativeViewEnabled: () => {},
                refreshConfig: async () => {},
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
        const headerColumnCount = within(rows[0]).getAllByRole("columnheader").length;

        const table = screen.getByRole("table");
        const footerRow = table.querySelector("tfoot tr") as HTMLTableRowElement;
        const footerColumnCount = Array.from(footerRow.children).reduce(
            (sum, cell) => sum + (Number(cell.getAttribute("colspan")) || 1),
            0,
        );

        expect(footerColumnCount).toBe(headerColumnCount);
    });

    it("shows each holding's sector, with a dash when unknown, and sorts by it", async () => {
        const sectorHoldings: Holding[] = [
            { ...holdings[0], ticker: "TECH", sector: "Technology" },
            { ...holdings[0], ticker: "BANK", sector: "Financials" },
            { ...holdings[0], ticker: "NONE", sector: "  " },
        ];
        renderWithConfig(<HoldingsTable holdings={sectorHoldings} />);

        const sectorHeader = await screen.findByRole("columnheader", { name: "Sector" });
        const tickerOrder = () =>
            screen
                .getAllByRole("row")
                .map((row) => within(row).queryByRole("button")?.textContent)
                .filter((ticker): ticker is string => ["TECH", "BANK", "NONE"].includes(ticker ?? ""));
        const sectorOf = (ticker: string) => {
            const row = screen.getByRole("button", { name: ticker }).closest("tr")!;
            const cells = within(row).getAllByRole("cell");
            return cells[2].textContent;
        };

        expect(sectorOf("TECH")).toBe("Technology");
        expect(sectorOf("BANK")).toBe("Financials");
        expect(sectorOf("NONE")).toBe("—");

        await userEvent.click(sectorHeader);
        expect(sectorHeader).toHaveTextContent("Sector ▲");
        expect(tickerOrder()).toEqual(["NONE", "BANK", "TECH"]);
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
        const cell = within(row!).getByText("✗ 10 days left");
        expect(cell).toBeInTheDocument();
        const expected = formatDateISO(new Date('2024-07-20'));
        expect(cell).toHaveAttribute('title', expected);
    });

    it("says a sale needs approval instead of a cryptic ✗ 0 (#7196)", async () => {
        render(<HoldingsTable holdings={holdings}/>);
        const row = (await screen.findByText("CAD Holding")).closest("tr");
        expect(within(row!).getByText("✗ Needs approval")).toBeInTheDocument();
        expect(within(row!).queryByText("✗ 0")).toBeNull();
    });

    it("says a sale needs approval for the null-countdown payload the backend now sends (#7242)", async () => {
        const blocked: Holding = { ...holdings[0], ticker: "APR", name: "Awaiting Approval", sell_eligible: false, days_until_eligible: null, next_eligible_sell_date: "2024-04-10" };
        render(<HoldingsTable holdings={[blocked]}/>);
        const row = (await screen.findByText("Awaiting Approval")).closest("tr");
        expect(within(row!).getByText("✗ Needs approval")).toBeInTheDocument();
    });

    it("gives no verdict when days until eligible is unknown (#7196)", async () => {
        const unknown: Holding = { ...holdings[0], ticker: "UNK", name: "Unknown Period", sell_eligible: false, days_until_eligible: null };
        render(<HoldingsTable holdings={[unknown]}/>);
        const row = (await screen.findByText("Unknown Period")).closest("tr");
        expect(within(row!).queryByText(/Needs approval/)).toBeNull();
        expect(within(row!).queryByText(/^✗/)).toBeNull();
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

    describe("FX rate source marker (#9730)", () => {
        const fxHolding = (ticker: string, fx_rate_source: string | null | undefined): Holding => ({
            ticker,
            name: `${ticker} Co`,
            currency: "USD",
            instrument_type: "Equity",
            units: 1,
            price: 80,
            cost_basis_gbp: 100,
            market_value_gbp: fx_rate_source === "missing" ? null : 80,
            gain_gbp: fx_rate_source === "missing" ? null : -20,
            current_price_gbp: fx_rate_source === "missing" ? null : 80,
            acquired_date: "2024-01-01",
            days_held: 10,
            sell_eligible: true,
            days_until_eligible: 0,
            fx_rate_source,
        });
        const fallbackTitle = () => i18n.t("holdingsTable.fxRateFallback");
        const missingTitle = () => i18n.t("holdingsTable.fxRateMissing");

        it("marks a holding valued at an approximate fallback rate", () => {
            render(<HoldingsTable holdings={[fxHolding("FBK", "fallback")]} />);
            const marker = screen.getByTitle(fallbackTitle());
            expect(marker).toHaveTextContent("≈");
            expect(marker).toHaveAccessibleName(fallbackTitle());
            expect(screen.queryByTitle(missingTitle())).toBeNull();
        });

        it("marks a holding with no FX rate distinctly", () => {
            render(<HoldingsTable holdings={[fxHolding("MIS", "missing")]} />);
            const marker = screen.getByTitle(missingTitle());
            expect(marker).toHaveTextContent("FX");
            expect(screen.queryByTitle(fallbackTitle())).toBeNull();
        });

        it.each(["live", "cache", null, undefined])("shows no marker for fx_rate_source %s", (source) => {
            render(<HoldingsTable holdings={[fxHolding("OK", source)]} />);
            expect(screen.queryByTitle(fallbackTitle())).toBeNull();
            expect(screen.queryByTitle(missingTitle())).toBeNull();
        });
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
        expect(within(rows[1]).getByText("AAA")).toBeInTheDocument();

        await userEvent.click(screen.getByText(/^Ticker/));
        rows = screen.getAllByRole("row");
        expect(within(rows[1]).getByText("XYZ")).toBeInTheDocument();
    });

    it("filters by ticker", async () => {
        render(<HoldingsTable holdings={holdings}/>);
        const input = await screen.findByPlaceholderText("Ticker");
        await userEvent.type(input, "AA");
        expect(screen.getByText("AAA")).toBeInTheDocument();
        expect(screen.queryByText("XYZ")).toBeNull();
    });

    it("renders a single header row with the filters outside the table (#7814)", async () => {
        render(<HoldingsTable holdings={holdings}/>);
        await screen.findByText("AAA");
        const table = screen.getByRole("table");
        expect(table.querySelectorAll("thead tr")).toHaveLength(1);
        const filters = screen.getByRole("group", { name: "Filter holdings" });
        expect(table.contains(filters)).toBe(false);
        expect(within(filters).getByLabelText("Filter by Ticker")).toBeInTheDocument();
    });

    it("keeps the filter inputs available when nothing matches (#7814)", async () => {
        render(<HoldingsTable holdings={holdings}/>);
        await userEvent.type(await screen.findByPlaceholderText("Ticker"), "missing");
        expect(screen.queryByRole("table")).toBeNull();
        expect(screen.getByPlaceholderText("Ticker")).toHaveValue("missing");
    });

    it("filters by eligibility", async () => {
        render(<HoldingsTable holdings={holdings}/>);
        const select = await screen.findByLabelText("Sell eligible");
        await userEvent.selectOptions(select, "true");
        expect(screen.getByText("AAA")).toBeInTheDocument();
        expect(screen.queryByText("Test Holding")).toBeNull();
    });

    it("excludes holdings with unknown (null) sell_eligible from both eligibility filter options (#7220 review follow-up)", async () => {
        // Regression guard: `!!h.sell_eligible !== expect` coerces
        // sell_eligible: null to false, which previously swept every
        // UNKNOWN-eligibility holding into the "No" filter result --
        // reporting "unknown" as a confident "not eligible", the exact class
        // of fabricated-certainty bug #7220 exists to remove. Unknown must
        // match neither "Yes" nor "No".
        const holdingsWithUnknown: Holding[] = [
            ...holdings,
            {
                ticker: "UNKN",
                name: "Unknown Eligibility",
                units: 3,
                acquired_date: null,
                days_held: null,
                sell_eligible: null,
                days_until_eligible: null,
            },
        ];

        render(<HoldingsTable holdings={holdingsWithUnknown} />);
        await screen.findByText("AAA");
        expect(screen.getByText("Unknown Eligibility")).toBeInTheDocument();

        const select = await screen.findByLabelText("Sell eligible");

        await userEvent.selectOptions(select, "true");
        expect(screen.getByText("AAA")).toBeInTheDocument();
        expect(screen.queryByText("Unknown Eligibility")).toBeNull();

        await userEvent.selectOptions(select, "false");
        expect(screen.getByText("Test Holding")).toBeInTheDocument();
        expect(screen.queryByText("Unknown Eligibility")).toBeNull();
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

      it("shows the more-columns hint only while columns remain off-screen (#7814)", () => {
          const clientWidth = vi.spyOn(HTMLElement.prototype, "clientWidth", "get");
          const scrollWidth = vi.spyOn(HTMLElement.prototype, "scrollWidth", "get");
          clientWidth.mockReturnValue(600);
          scrollWidth.mockReturnValue(1200);
          try {
              render(<HoldingsTable holdings={holdings} />);
              const tableContainer = screen.getByRole('table').parentElement as HTMLElement;
              expect(screen.getByText("More columns →")).toBeInTheDocument();

              tableContainer.scrollLeft = 600;
              fireEvent.scroll(tableContainer);
              expect(screen.queryByText("More columns →")).toBeNull();
          } finally {
              clientWidth.mockRestore();
              scrollWidth.mockRestore();
          }
      });

      it("does not show the more-columns hint when every column fits", () => {
          render(<HoldingsTable holdings={holdings} />);
          expect(screen.queryByText("More columns →")).toBeNull();
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
          // real api layer; stub fetch so /instrument/batch resolves to every
          // held ticker landing in the "empty" (no rows) bucket.
          vi.stubGlobal(
              "fetch",
              vi.fn((input: RequestInfo | URL) => {
                  const url = typeof input === "string" ? input : input.toString();
                  if (url.includes("/instrument/batch")) {
                      return Promise.resolve({
                          ok: true,
                          json: async () => ({
                              instruments: {},
                              empty: holdings.map((h) => h.ticker),
                              unknown: [],
                          }),
                      } as Response);
                  }
                  return Promise.resolve({
                      ok: true,
                      json: async () => ({
                          prices: [],
                          mini: { 7: [], 30: [], 180: [] },
                          positions: [],
                      }),
                  } as Response);
              }),
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

  describe("column presets (#7832)", () => {
      const headerTitles = (container: HTMLElement) =>
          Array.from(container.querySelector("thead tr")!.querySelectorAll("th")).map(
              (th) => th.textContent?.replace(/[▲▼]/g, "").trim(),
          );
      const presetButton = (name: string) =>
          within(screen.getByRole("group", { name: "Column preset:" })).getByRole("button", {
              name,
          });

      it("defaults to the Simple preset when no column choice is saved", () => {
          localStorage.removeItem(COLUMN_VISIBILITY_STORAGE_KEY);
          const { container } = render(<HoldingsTable holdings={holdings} />);

          expect(headerTitles(container)).toEqual(["Ticker", "Name", "Units", "Mkt £", "Gain £"]);
          expect(presetButton("Simple")).toHaveAttribute("aria-pressed", "true");
          expect(presetButton("Detailed")).toHaveAttribute("aria-pressed", "false");
          expect(screen.getByRole("checkbox", { name: "Units" })).toBeChecked();
          expect(screen.getByRole("checkbox", { name: "Sector" })).not.toBeChecked();
          // Total row label spans ticker + name only, so the footer stays aligned.
          const footerCells = container.querySelectorAll("tfoot td");
          expect(footerCells[0]).toHaveAttribute("colspan", "2");
          expect(footerCells).toHaveLength(4);
      });

      it("Detailed restores the full column set, checks every box and is saved", async () => {
          localStorage.removeItem(COLUMN_VISIBILITY_STORAGE_KEY);
          const { container, unmount } = render(<HoldingsTable holdings={holdings} />);

          await userEvent.click(presetButton("Detailed"));

          expect(headerTitles(container)).toHaveLength(19);
          expect(presetButton("Detailed")).toHaveAttribute("aria-pressed", "true");
          // With sector shown, the total row label spans ticker + name + sector.
          expect(container.querySelector("tfoot td")).toHaveAttribute("colspan", "3");
          const columnCheckboxes = within(
              screen.getByRole("group", { name: "Columns:" }),
          ).getAllByRole("checkbox");
          expect(columnCheckboxes).toHaveLength(17);
          for (const checkbox of columnCheckboxes) {
              expect(checkbox).toBeChecked();
          }
          expect(JSON.parse(localStorage.getItem(COLUMN_VISIBILITY_STORAGE_KEY)!)).toEqual(
              DETAILED_COLUMNS,
          );

          unmount();
          const { container: remounted } = render(<HoldingsTable holdings={holdings} />);
          expect(headerTitles(remounted)).toHaveLength(19);
      });

      it("keeps per-column checkboxes working on top of a preset", async () => {
          localStorage.removeItem(COLUMN_VISIBILITY_STORAGE_KEY);
          const { container } = render(<HoldingsTable holdings={holdings} />);

          await userEvent.click(screen.getByRole("checkbox", { name: "Sector" }));

          expect(headerTitles(container)).toContain("Sector");
          expect(presetButton("Simple")).toHaveAttribute("aria-pressed", "false");
          expect(presetButton("Detailed")).toHaveAttribute("aria-pressed", "false");

          await userEvent.click(presetButton("Simple"));
          expect(headerTitles(container)).not.toContain("Sector");
          expect(screen.getByRole("checkbox", { name: "Sector" })).not.toBeChecked();
      });

      it("relative view still hides money columns a preset turns on, until it is switched off", async () => {
          localStorage.removeItem(COLUMN_VISIBILITY_STORAGE_KEY);
          const { container } = renderWithConfig(<HoldingsTable holdings={holdings} />);
          await userEvent.click(screen.getByLabelText("Relative view"));

          await userEvent.click(presetButton("Detailed"));

          expect(presetButton("Detailed")).toHaveAttribute("aria-pressed", "true");
          expect(screen.getByRole("checkbox", { name: "Units" })).toBeChecked();
          const relativeHeaders = headerTitles(container);
          for (const hidden of ["Units", "Mkt £", "Gain £", "Total return £", "Income £", "Cost £"]) {
              expect(relativeHeaders).not.toContain(hidden);
          }
          expect(relativeHeaders).toContain("Gain %");
          expect(relativeHeaders).toHaveLength(13);

          await userEvent.click(screen.getByLabelText("Relative view"));
          expect(headerTitles(container)).toHaveLength(19);
      });

      it.each([
          ["Simple", null],
          ["Detailed", DETAILED_COLUMNS],
          ["a custom mix", { ...DETAILED_COLUMNS, sector: false, weight_pct: false, trend: false }],
      ])(
          "keeps every grouped row aligned with an account column under %s",
          async (_label, saved) => {
              if (saved) {
                  localStorage.setItem(COLUMN_VISIBILITY_STORAGE_KEY, JSON.stringify(saved));
              } else {
                  localStorage.removeItem(COLUMN_VISIBILITY_STORAGE_KEY);
              }
              const accountHoldings = holdings.map((h, index) => ({
                  ...h,
                  source_account: "isa",
                  grouping: index % 2 ? "Growth" : "Income",
              }));
              const { container } = renderWithConfig(
                  <HoldingsTable holdings={accountHoldings} showAccount groupingMode="group" />,
              );
              for (const toggle of screen.getAllByRole("button", { name: /^Toggle / })) {
                  await userEvent.click(toggle);
              }

              const widths = Array.from(container.querySelectorAll("table tr")).map((row) =>
                  Array.from(row.children).reduce(
                      (sum, cell) => sum + ((cell as HTMLTableCellElement).colSpan || 1),
                      0,
                  ),
              );
              const headerWidth = container.querySelector("thead tr")!.children.length;
              // The single header row (#7814), two group headers, holding rows
              // and the total row.
              expect(widths.length).toBe(holdings.length + 4);
              expect(new Set(widths)).toEqual(new Set([headerWidth]));
          },
      );

      it("falls back to Simple when the saved choice is unreadable", () => {
          localStorage.setItem(COLUMN_VISIBILITY_STORAGE_KEY, "{not json");
          const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
          const { container } = render(<HoldingsTable holdings={holdings} />);

          expect(headerTitles(container)).toEqual(["Ticker", "Name", "Units", "Mkt £", "Gain £"]);
          expect(warn).toHaveBeenCalled();
          warn.mockRestore();
      });
  });
  });
