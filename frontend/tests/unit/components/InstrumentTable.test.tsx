import { render, screen, fireEvent, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, afterEach, type Mock } from "vitest";
import { useState } from "react";
import type { InstrumentSummary } from "@/types";
import { configContext, type AppConfig } from "@/ConfigContext";

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

const {
    listInstrumentGroupsMock,
    assignInstrumentGroupMock,
    createInstrumentGroupMock,
    clearInstrumentGroupMock,
} = vi.hoisted(() => ({
    listInstrumentGroupsMock: vi.fn(async () => ["Group A", "Group B"]),
    assignInstrumentGroupMock: vi.fn(async () => ({
        status: "assigned",
        group: "Group B",
        groups: ["Group A", "Group B"],
    })),
    createInstrumentGroupMock: vi.fn(async () => ({
        status: "created",
        group: "New Group",
        groups: ["Group A", "Group B", "New Group"],
    })),
    clearInstrumentGroupMock: vi.fn(async () => ({ status: "cleared" })),
}));

vi.mock("@/api", () => ({
    listInstrumentGroups: listInstrumentGroupsMock,
    assignInstrumentGroup: assignInstrumentGroupMock,
    createInstrumentGroup: createInstrumentGroupMock,
    clearInstrumentGroup: clearInstrumentGroupMock,
}));

vi.mock("@/components/InstrumentDetail", () => ({
    InstrumentDetail: vi.fn(() => <div data-testid="instrument-detail" />),
}));

import { InstrumentTable } from "@/components/InstrumentTable";
import { InstrumentDetail } from "@/components/InstrumentDetail";
afterEach(() => {
    vi.clearAllMocks();
});

describe("InstrumentTable", () => {
    const rows: InstrumentSummary[] = [
        {
            ticker: "ABC",
            name: "ABC Corp",
            grouping: "Group A",
            exchange: "L",
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
            exchange: "N",
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
            exchange: "L",
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
            exchange: "T",
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

    const getSummaryButton = (title: string) =>
        screen.getByRole("button", { name: new RegExp(`Toggle ${title}`, "i") });

    const getSummaryRow = (title: string) => {
        const button = getSummaryButton(title);
        const row = button.closest("tr");
        if (!row) {
            throw new Error(`Summary row for ${title} not found`);
        }
        return row as HTMLTableRowElement;
    };

    const openGroup = (title: string) => {
        const button = getSummaryButton(title);
        if (button.getAttribute("aria-expanded") !== "true") {
            fireEvent.click(button);
        }
        return button;
    };

    const getGroupTickers = (title: string) => {
        const summaryRow = getSummaryRow(title);
        const tickers: string[] = [];
        let current = summaryRow.nextElementSibling as HTMLTableRowElement | null;
        while (current) {
            const cell = current.cells[0];
            if (!cell) {
                break;
            }
            const tickerButton = cell.querySelector("button");
            if (!tickerButton) {
                break;
            }
            tickers.push(tickerButton.textContent ?? "");
            current = current.nextElementSibling as HTMLTableRowElement | null;
        }
        return tickers;
    };

    const getGroupOrder = () =>
        screen
            .getAllByRole("button", { name: /^Toggle / })
            .map((button) => {
                const spans = button.querySelectorAll("span");
                if (spans.length >= 2) {
                    return spans[1]?.textContent ?? "";
                }
                const label = button.getAttribute("aria-label");
                return label ? label.replace(/^Toggle\s+/, "") : "";
            });

    const expectGroupsCollapsed = () => {
        screen
            .getAllByRole("button", { name: /^Toggle / })
            .forEach((button) =>
                expect(button).toHaveAttribute("aria-expanded", "false"),
            );
    };

    it("renders groups collapsed by default with aggregated totals", () => {
        render(<InstrumentTable rows={rows} />);
        const table = screen.getByRole("table");
        expect(table).toBeInTheDocument();

        const groupASummary = getSummaryRow("Group A");
        expect(within(groupASummary).getByText("£1,500.00")).toBeInTheDocument();
        expect(within(groupASummary).getByText("▲£50.00")).toBeInTheDocument();
        expect(within(groupASummary).getByText("▲3.4%")).toBeInTheDocument();
        expect(within(groupASummary).getByText("▲0.3%")).toBeInTheDocument();
        expect(within(groupASummary).getByText("▲0.7%")).toBeInTheDocument();

        expect(screen.queryByText("ABC")).toBeNull();

        openGroup("Group A");
        expect(screen.getByText("ABC")).toBeInTheDocument();
    });

    it("filters rows by exchange selection", async () => {
        render(<InstrumentTable rows={rows} />);
        expect(screen.getByText("Exchanges:")).toBeInTheDocument();

        const lCheckbox = screen.getByLabelText("L");
        const nCheckbox = screen.getByLabelText("N");
        const tCheckbox = screen.getByLabelText("T");

        expect(lCheckbox).toBeChecked();
        expect(nCheckbox).toBeChecked();
        expect(tCheckbox).toBeChecked();

        openGroup("Group A");
        openGroup("Group B");
        openGroup("Ungrouped");

        expect(screen.getByText("ABC")).toBeInTheDocument();
        expect(screen.getByText("XYZ")).toBeInTheDocument();
        expect(screen.getByText("DEF")).toBeInTheDocument();
        expect(screen.getByText("CADI")).toBeInTheDocument();

        fireEvent.click(lCheckbox);
        expect(lCheckbox).not.toBeChecked();
        expect(screen.queryByText("ABC")).toBeNull();
        expect(screen.queryByText("DEF")).toBeNull();
        expect(screen.getByText("XYZ")).toBeInTheDocument();

        fireEvent.click(nCheckbox);
        expect(nCheckbox).not.toBeChecked();
        expect(screen.queryByText("XYZ")).toBeNull();
        expect(screen.getByText("CADI")).toBeInTheDocument();

        fireEvent.click(tCheckbox);
        expect(tCheckbox).not.toBeChecked();
        await waitFor(() => expect(screen.getByText("No instruments.")).toBeInTheDocument());

        fireEvent.click(lCheckbox);
        expect(lCheckbox).toBeChecked();
        openGroup("Group A");
        await waitFor(() => expect(screen.getByText("ABC")).toBeInTheDocument());
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
        let tickers = getGroupTickers("Group A");
        expect(tickers[0]).toBe("ABC");

        fireEvent.click(within(screen.getByRole("table")).getByText(/^Ticker/));
        tickers = getGroupTickers("Group A");
        expect(tickers[0]).toBe("XYZ");
    });


    it("keeps cash instruments ahead of others across sort orders", () => {
        const mixedRows: InstrumentSummary[] = [
            {
                ticker: "BETA",
                name: "Beta PLC",
                currency: "GBP",
                instrument_type: "Equity",
                units: 10,
                market_value_gbp: 1000,
                gain_gbp: 50,
            },
            {
                ticker: "CASHGBP",
                name: "Cash Balance",
                currency: "GBP",
                instrument_type: "Cash",
                units: 1,
                market_value_gbp: 200,
                gain_gbp: 0,
            },
            {
                ticker: "ALPHA",
                name: "Alpha Corp",
                currency: "USD",
                instrument_type: "Equity",
                units: 5,
                market_value_gbp: 500,
                gain_gbp: 25,
            },
            {
                ticker: "CASHALT",
                name: "Alt Cash",
                currency: "EUR",
                instrument_type: "ETF",
                units: 2,
                market_value_gbp: 150,
                gain_gbp: 5,
            },
        ];

        render(<InstrumentTable rows={mixedRows} />);
        openGroup("Ungrouped");

        const table = screen.getByRole("table");
        const tickerHeader = within(table).getByText(/^Ticker/);

        let tickers = getGroupTickers("Ungrouped");
        expect(tickers).toEqual(["CASHALT", "CASHGBP", "ALPHA", "BETA"]);

        fireEvent.click(tickerHeader);

        tickers = getGroupTickers("Ungrouped");
        expect(tickers).toEqual(["CASHGBP", "CASHALT", "BETA", "ALPHA"]);
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

    it("assigns an existing group via the action menu", async () => {
        renderWithConfig(<InstrumentTable rows={rows} />);
        openGroup("Group A");
        await waitFor(() => expect(listInstrumentGroupsMock).toHaveBeenCalled());
        const select = screen.getByLabelText("Change group for ABC");
        fireEvent.change(select, { target: { value: "Group B" } });

        await waitFor(() => expect(assignInstrumentGroupMock).toHaveBeenCalledWith("ABC", "L", "Group B"));
        const container = select.parentElement as HTMLElement;
        await waitFor(() => expect(within(container).getByText("Group B")).toBeInTheDocument());
    });

    it("creates a new group and assigns it", async () => {
        createInstrumentGroupMock.mockResolvedValueOnce({
            status: "created",
            group: "Income",
            groups: ["Group A", "Group B", "Income"],
        });
        assignInstrumentGroupMock.mockResolvedValueOnce({
            status: "assigned",
            group: "Income",
            groups: ["Group A", "Group B", "Income"],
        });
        const promptSpy = vi.spyOn(window, "prompt").mockReturnValue(" Income ");

        renderWithConfig(<InstrumentTable rows={rows} />);
        openGroup("Group A");
        await waitFor(() => expect(listInstrumentGroupsMock).toHaveBeenCalled());
        const select = screen.getByLabelText("Change group for ABC");
        fireEvent.change(select, { target: { value: "__create__" } });

        await waitFor(() => expect(createInstrumentGroupMock).toHaveBeenCalledWith("Income"));
        await waitFor(() => expect(assignInstrumentGroupMock).toHaveBeenCalledWith("ABC", "L", "Income"));
        const container = select.parentElement as HTMLElement;
        await waitFor(() => expect(within(container).getByText("Income")).toBeInTheDocument());
        promptSpy.mockRestore();
    });

    it("clears an assigned group", async () => {
        renderWithConfig(<InstrumentTable rows={rows} />);
        openGroup("Group A");
        await waitFor(() => expect(listInstrumentGroupsMock).toHaveBeenCalled());
        const select = screen.getByLabelText("Change group for ABC");
        fireEvent.change(select, { target: { value: "__clear__" } });

        await waitFor(() => expect(clearInstrumentGroupMock).toHaveBeenCalledWith("ABC", "L"));
        const container = select.parentElement as HTMLElement;
        await waitFor(() => expect(within(container).getByText("—")).toBeInTheDocument());
    });
});
