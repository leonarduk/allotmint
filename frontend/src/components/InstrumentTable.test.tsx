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
        expect(within(dataRows[1]).getByText("ABC")).toBeInTheDocument();

        fireEvent.click(screen.getByText(/^Ticker/));
        dataRows = screen.getAllByRole("row");
        expect(within(dataRows[1]).getByText("XYZ")).toBeInTheDocument();
    });

    it("renders 7d and 30d percentage changes", () => {
        render(<InstrumentTable rows={rows} />);
        expect(screen.getByText("1.0%"));
        expect(screen.getByText("2.0%"));
        expect(screen.getByText("-1.0%"));
        expect(screen.getByText("-2.0%"));
    });
});
