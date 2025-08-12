import { render, screen, within, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { HoldingsTable } from "./HoldingsTable";
import { ConfigContext, type AppConfig } from "../ConfigContext";
import type { Holding } from "../types";

describe("HoldingsTable", () => {
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
            acquired_date: "2024-01-01",
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
        },
    ];

    const renderWithConfig = (ui: React.ReactElement, cfg: AppConfig) =>
        render(<ConfigContext.Provider value={cfg}>{ui}</ConfigContext.Provider>);

    it("displays relative metrics when relative view is enabled", () => {
        renderWithConfig(<HoldingsTable holdings={holdings} />, { relativeViewEnabled: true });
        expect(screen.getByText("AAA")).toBeInTheDocument();
        expect(screen.getByText("XYZ")).toBeInTheDocument();
        expect(screen.getByRole('columnheader', {name: /Gain %/})).toBeInTheDocument();
        expect(screen.getByRole('columnheader', {name: /Weight %/})).toBeInTheDocument();
        expect(screen.queryByRole('columnheader', {name: 'Units'})).toBeNull();
        expect(screen.queryByRole('columnheader', {name: /Cost £/})).toBeNull();
        expect(screen.queryByRole('columnheader', {name: /Gain £/})).toBeNull();
        expect(screen.queryByRole('columnheader', {name: /Mkt £/})).toBeNull();
    });

    it("opens currency pair when currency clicked", () => {
        const onSelect = vi.fn();
        render(<HoldingsTable holdings={holdings} onSelectInstrument={onSelect} />);
        fireEvent.click(screen.getByRole("button", { name: "USD" }));
        expect(onSelect).toHaveBeenCalledWith({
            ticker: "GBPUSD",
            name: "GBPUSD",
            currency: "USD",
        });
    });

    it("shows absolute columns when relative view is disabled", () => {
        renderWithConfig(<HoldingsTable holdings={holdings} />, { relativeViewEnabled: false });
        expect(screen.getByRole('columnheader', {name: 'Units'})).toBeInTheDocument();
        expect(screen.getByRole('columnheader', {name: /Cost £/})).toBeInTheDocument();
        expect(screen.getByRole('columnheader', {name: /Gain £/})).toBeInTheDocument();
        expect(screen.getByRole('columnheader', {name: /Mkt £/})).toBeInTheDocument();
    });

    it("shows days to go if not eligible", () => {
        render(<HoldingsTable holdings={holdings}/>);
        const row = screen.getByText("Test Holding").closest("tr");
        const cell = within(row!).getByText("✗ 10");
        expect(cell).toBeInTheDocument();
    });

    it("sorts by ticker when header clicked", () => {
        render(<HoldingsTable holdings={holdings}/>);
        // initially sorted ascending by ticker => AAA first
        let rows = screen.getAllByRole("row");
        expect(within(rows[2]).getByText("AAA")).toBeInTheDocument();

        fireEvent.click(screen.getByText(/^Ticker/));
        rows = screen.getAllByRole("row");
        expect(within(rows[2]).getByText("XYZ")).toBeInTheDocument();
    });

    it("filters by ticker", () => {
        render(<HoldingsTable holdings={holdings}/>);
        const input = screen.getByPlaceholderText("Ticker");
        fireEvent.change(input, { target: { value: "AA" } });
        expect(screen.getByText("AAA")).toBeInTheDocument();
        expect(screen.queryByText("XYZ")).toBeNull();
    });

    it("filters by eligibility", () => {
        render(<HoldingsTable holdings={holdings}/>);
        const select = screen.getByLabelText("Sell eligible");
        fireEvent.change(select, { target: { value: "true" } });
        expect(screen.getByText("AAA")).toBeInTheDocument();
        expect(screen.queryByText("Test Holding")).toBeNull();
    });

    it("allows toggling columns", () => {
        render(<HoldingsTable holdings={holdings}/>);
        expect(screen.getByRole('columnheader', {name: 'Units'})).toBeInTheDocument();
        const checkbox = screen.getByLabelText("Units");
        fireEvent.click(checkbox);
        expect(screen.queryByRole('columnheader', {name: 'Units'})).toBeNull();
    });
});
