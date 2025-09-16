import { render, screen, fireEvent, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, type Mock } from "vitest";
import { useState } from "react";
import type { InstrumentSummary } from "../types";
import { configContext, type AppConfig } from "../ConfigContext";

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
        profile: true,
        pension: true,
        reports: true,
        scenario: true,
        logs: true,
    },
};

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

vi.mock("./InstrumentDetail", () => ({
    InstrumentDetail: vi.fn(() => <div data-testid="instrument-detail" />),
}));

import { InstrumentTable } from "./InstrumentTable";
import { InstrumentDetail } from "./InstrumentDetail";

describe("InstrumentTable", () => {
    const rows: InstrumentSummary[] = [
        {
            ticker: "ABC",
            name: "ABC Corp",
            grouping: "Group A",
            currency: "GBP",
            instrument_type: "Equity",
            units: 10,
            market_value_gbp: 1000,
            gain_gbp: 100,
            last_price_gbp: 100,
            last_price_date: "2024-01-01",
            change_7d_pct: 1,
            change_30d_pct: 2,
        },
        {
            ticker: "XYZ",
            name: "XYZ Inc",
            grouping: "Group A",
            currency: "USD",
            instrument_type: "Equity",
            units: 5,
            market_value_gbp: 500,
            gain_gbp: -50,
            last_price_gbp: 50,
            last_price_date: "2024-01-02",
            change_7d_pct: -1,
            change_30d_pct: -2,
        },
        {
            ticker: "DEF",
            name: "DEF Ltd",
            grouping: "Group B",
            currency: "GBX",
            instrument_type: "Equity",
            units: 3,
            market_value_gbp: 300,
            gain_gbp: 30,
            last_price_gbp: 10,
            last_price_date: "2024-01-03",
            change_7d_pct: 0.5,
            change_30d_pct: 1,
        },
        {
            ticker: "CADI",
            name: "CAD Inc",
            currency: "CAD",
            instrument_type: "Equity",
            units: 2,
            market_value_gbp: 200,
            gain_gbp: 20,
            last_price_gbp: 100,
            last_price_date: "2024-01-04",
            change_7d_pct: 0,
            change_30d_pct: 0,
        },
    ];

    const getGroupHeader = (title: string) => {
        const heading = screen.getByRole("heading", { name: title });
        const container = heading.parentElement?.parentElement;
        if (!container) {
            throw new Error(`Group header for ${title} not found`);
        }
        return container as HTMLElement;
    };

    const openGroup = (title: string) => {
        const header = getGroupHeader(title);
        const toggle = header.querySelector<HTMLButtonElement>('button[aria-label="Expand"]');
        if (!toggle) {
            throw new Error(`Expand button for ${title} not found`);
        }
        fireEvent.click(toggle);
        return header;
    };

    it("renders groups collapsed by default with aggregated totals", () => {
        render(<InstrumentTable rows={rows} />);
        expect(screen.getByText("Group A")).toBeInTheDocument();
        expect(screen.getByText("Group B")).toBeInTheDocument();
        expect(screen.getByText("Ungrouped")).toBeInTheDocument();
        expect(screen.queryByRole('table')).toBeNull();

        const groupAHeader = getGroupHeader("Group A");
        expect(within(groupAHeader).getByText("Market")).toBeInTheDocument();
        expect(within(groupAHeader).getByText("£1,500.00")).toBeInTheDocument();
        expect(within(groupAHeader).getByText("▲£50.00")).toBeInTheDocument();
        expect(within(groupAHeader).getByText("▲3.4%")).toBeInTheDocument();
        expect(within(groupAHeader).getByText("▲0.3%")).toBeInTheDocument();
        expect(within(groupAHeader).getByText("▲0.7%")).toBeInTheDocument();

        expect(screen.queryByText("ABC")).toBeNull();

        openGroup("Group A");
        expect(screen.getByText("ABC")).toBeInTheDocument();
    });

    it("passes ticker and name to InstrumentDetail", () => {
        render(<InstrumentTable rows={rows} />);
        openGroup("Group A");
        expect(screen.getByText("GBP")).toBeInTheDocument();
        fireEvent.click(screen.getByText("ABC"));

        const mock = InstrumentDetail as unknown as Mock;
        expect(mock).toHaveBeenCalled();
        type DetailProps = Parameters<typeof InstrumentDetail>[0];
        const props = mock.mock.calls[0][0] as DetailProps;
        expect(props.ticker).toBe("ABC");
        expect(props.name).toBe("ABC Corp");
    });

    it("creates FX pair ticker buttons and skips GBX", () => {
        const mock = InstrumentDetail as unknown as Mock;
        mock.mockClear();
        render(<InstrumentTable rows={rows} />);
        openGroup("Group A");
        openGroup("Group B");
        openGroup("Ungrouped");
        fireEvent.click(screen.getByRole('button', { name: 'USD' }));
        expect(mock).toHaveBeenCalled();
        type DetailProps = Parameters<typeof InstrumentDetail>[0];
        const props = mock.mock.calls[0][0] as DetailProps;
        expect(props.ticker).toBe('USDGBP.FX');
        expect(screen.queryByRole('button', { name: 'GBX' })).toBeNull();
        expect(screen.getByRole('button', { name: 'CAD' })).toBeInTheDocument();
    });

    it("sorts by ticker when header clicked", () => {
        render(<InstrumentTable rows={rows} />);
        openGroup("Group A");
        // initial sort is ticker ascending => ABC first
        let table = screen.getByRole("table");
        let dataRows = within(table).getAllByRole("row");
        expect(within(dataRows[1]).getByText("ABC")).toBeInTheDocument();

        fireEvent.click(within(table).getByText(/^Ticker/));
        table = screen.getByRole("table");
        dataRows = within(table).getAllByRole("row");
        expect(within(dataRows[1]).getByText("XYZ")).toBeInTheDocument();
    });

    it("allows toggling columns", () => {
        render(<InstrumentTable rows={rows} />);
        openGroup("Group A");
        const table = screen.getByRole('table');
        expect(within(table).getByRole('columnheader', {name: /Gain %/})).toBeInTheDocument();
        const checkbox = screen.getByLabelText("Gain %");
        fireEvent.click(checkbox);
        expect(within(screen.getByRole('table')).queryByRole('columnheader', {name: /Gain %/})).toBeNull();
    });

    it("shows absolute columns when relative view disabled", () => {
        render(<InstrumentTable rows={rows} />);
        openGroup("Group A");
        const table = screen.getByRole('table');
        expect(within(table).getByRole('columnheader', { name: 'Units' })).toBeInTheDocument();
        expect(within(table).getByRole('columnheader', { name: 'Cost £' })).toBeInTheDocument();
        expect(within(table).getByRole('columnheader', { name: 'Market £' })).toBeInTheDocument();
        expect(within(table).getByRole('columnheader', { name: 'Gain £' })).toBeInTheDocument();
        expect(within(table).getByRole('columnheader', { name: 'Last £' })).toBeInTheDocument();
    });

    it("toggles relative view to hide absolute columns", async () => {
        renderWithConfig(<InstrumentTable rows={rows} />);
        openGroup("Group A");
        const table = () => screen.getByRole('table');
        expect(within(table()).getByRole('columnheader', { name: 'Units' })).toBeInTheDocument();
        const toggle = screen.getByLabelText('Relative view');
        await userEvent.click(toggle);
        const updatedTable = table();
        expect(within(updatedTable).queryByRole('columnheader', { name: 'Units' })).toBeNull();
        expect(within(updatedTable).queryByRole('columnheader', { name: 'Cost £' })).toBeNull();
        expect(within(updatedTable).queryByRole('columnheader', { name: 'Market £' })).toBeNull();
        expect(within(updatedTable).queryByRole('columnheader', { name: 'Gain £' })).toBeNull();
        expect(within(updatedTable).queryByRole('columnheader', { name: 'Last £' })).toBeNull();
        expect(within(updatedTable).getByRole('columnheader', { name: 'Gain %' })).toBeInTheDocument();
    });
});
