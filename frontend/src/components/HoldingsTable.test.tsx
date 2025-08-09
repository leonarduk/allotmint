import {render, screen, within, fireEvent} from "@testing-library/react";
import {HoldingsTable} from "./HoldingsTable";
import type {Holding} from "../types";

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

    it("displays table rows for each holding", () => {
        render(<HoldingsTable holdings={holdings} total_value_estimate_gbp={150}/>);
        expect(screen.getByText("AAA")).toBeInTheDocument();
        expect(screen.getByText("XYZ")).toBeInTheDocument();
        expect(screen.getByText(/Gain %/)).toBeInTheDocument();
        expect(screen.getByText(/Weight %/)).toBeInTheDocument();
        expect(screen.getByText("Test Holding")).toBeInTheDocument();
        expect(screen.getByText("GBP")).toBeInTheDocument();
        expect(screen.getAllByText("5").length).toBeGreaterThan(0);
    });

    it("shows days to go if not eligible", () => {
        render(<HoldingsTable holdings={holdings} total_value_estimate_gbp={150}/>);
        const row = screen.getByText("Test Holding").closest("tr");
        const cell = within(row!).getByText("✗ 10");
        expect(cell).toBeInTheDocument();
    });

    it("sorts by ticker when header clicked", () => {
        render(<HoldingsTable holdings={holdings} total_value_estimate_gbp={150}/>);
        // initially sorted ascending by ticker => AAA first
        let rows = screen.getAllByRole("row");
        expect(within(rows[1]).getByText("AAA")).toBeInTheDocument();

        fireEvent.click(screen.getByText(/^Ticker/));
        rows = screen.getAllByRole("row");
        expect(within(rows[1]).getByText("XYZ")).toBeInTheDocument();
    });
});
