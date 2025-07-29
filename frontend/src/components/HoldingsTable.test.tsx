import {render, screen, within} from "@testing-library/react";
import {HoldingsTable} from "./HoldingsTable";
import type {Holding} from "../types";

describe("HoldingsTable", () => {
    const holdings: Holding[] = [
        {
            ticker: "XYZ",
            name: "Test Holding",
            units: 5,
            price: 0,
            cost_basis_gbp: 500,
            market_value_gbp: 0,
            gain_gbp: -25,
            acquired_date: null,
            days_held: null,
            sell_eligible: false,
            days_until_eligible: 10,
        },
    ];

    it("displays table rows for each holding", () => {
        render(<HoldingsTable holdings={holdings}/>);
        expect(screen.getByText("XYZ")).toBeInTheDocument();
        expect(screen.getByText("Test Holding")).toBeInTheDocument();
        expect(screen.getByText("5")).toBeInTheDocument();
    });

    it("shows days to go if not eligible", () => {
        render(<HoldingsTable holdings={holdings}/>);
        const row = screen.getByText("Test Holding").closest("tr");
        const cell = within(row!).getByText("✗ 10");
        expect(cell).toBeInTheDocument();
    });
});
