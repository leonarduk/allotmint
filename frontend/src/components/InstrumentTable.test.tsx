import { render, screen, fireEvent, within } from "@testing-library/react";
import { describe, it, expect, vi, type Mock } from "vitest";
import type { InstrumentSummary } from "../types";

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
    ];

    it("passes ticker and name to InstrumentDetail", () => {
        render(<InstrumentTable rows={rows} />);
        expect(screen.getByText("GBP")).toBeInTheDocument();
        fireEvent.click(screen.getByText("ABC"));

        const mock = InstrumentDetail as unknown as Mock;
        expect(mock).toHaveBeenCalled();
        type DetailProps = Parameters<typeof InstrumentDetail>[0];
        const props = mock.mock.calls[0][0] as DetailProps;
        expect(props.ticker).toBe("ABC");
        expect(props.name).toBe("ABC Corp");
    });

    it("sorts by ticker when header clicked", () => {
        render(<InstrumentTable rows={rows} />);
        // initial sort is ticker ascending => ABC first
        let dataRows = screen.getAllByRole("row");
        // header row + filter row => first data row at index 2
        expect(within(dataRows[2]).getByText("ABC")).toBeInTheDocument();

        fireEvent.click(screen.getByText(/^Ticker/));
        dataRows = screen.getAllByRole("row");
        expect(within(dataRows[2]).getByText("XYZ")).toBeInTheDocument();
    });

    it("filters rows by name", () => {
        render(<InstrumentTable rows={rows} />);
        const input = screen.getByLabelText("name filter");
        fireEvent.change(input, { target: { value: "XYZ" } });

        expect(screen.queryByText("ABC Corp")).not.toBeInTheDocument();
        expect(screen.getByText("XYZ Inc")).toBeInTheDocument();
        // header row + filter row + one data row
        expect(screen.getAllByRole("row")).toHaveLength(3);
    });
});
