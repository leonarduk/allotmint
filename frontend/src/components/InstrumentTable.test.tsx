import { render, screen, fireEvent, within } from "@testing-library/react";
import { describe, it, expect, vi, type Mock } from "vitest";
import type { InstrumentSummary } from "../types";
import { ConfigContext } from "../ConfigContext";

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
        expect(props.currency).toBe("GBP");
    });

    it("opens currency pair when currency clicked", () => {
        render(<InstrumentTable rows={rows} />);
        fireEvent.click(screen.getByRole("button", { name: "USD" }));

        const mock = InstrumentDetail as unknown as Mock;
        const props = mock.mock.calls.at(-1)[0] as Parameters<typeof InstrumentDetail>[0];
        expect(props.ticker).toBe("GBPUSD");
        expect(props.name).toBe("GBPUSD");
        expect(props.currency).toBe("USD");
    });

    it("disables currency button for GBP", () => {
        render(<InstrumentTable rows={rows} />);
        const btn = screen.getByRole("button", { name: "GBP" });
        expect(btn).toBeDisabled();
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

    it("allows toggling columns", () => {
        render(<InstrumentTable rows={rows} />);
        expect(screen.getByRole('columnheader', {name: /Gain %/})).toBeInTheDocument();
        const checkbox = screen.getByLabelText("Gain %");
        fireEvent.click(checkbox);
        expect(screen.queryByRole('columnheader', {name: /Gain %/})).toBeNull();
    });

    it("shows absolute columns when relative view disabled", () => {
        render(<InstrumentTable rows={rows} />);
        expect(screen.getByRole('columnheader', { name: 'Units' })).toBeInTheDocument();
        expect(screen.getByRole('columnheader', { name: 'Cost £' })).toBeInTheDocument();
        expect(screen.getByRole('columnheader', { name: 'Market £' })).toBeInTheDocument();
        expect(screen.getByRole('columnheader', { name: 'Gain £' })).toBeInTheDocument();
        expect(screen.getByRole('columnheader', { name: 'Last £' })).toBeInTheDocument();
    });

    it("hides absolute columns in relative view", () => {
        render(
            <ConfigContext.Provider value={{ relativeViewEnabled: true }}>
                <InstrumentTable rows={rows} />
            </ConfigContext.Provider>,
        );
        expect(screen.queryByRole('columnheader', { name: 'Units' })).toBeNull();
        expect(screen.queryByRole('columnheader', { name: 'Cost £' })).toBeNull();
        expect(screen.queryByRole('columnheader', { name: 'Market £' })).toBeNull();
        expect(screen.queryByRole('columnheader', { name: 'Gain £' })).toBeNull();
        expect(screen.queryByRole('columnheader', { name: 'Last £' })).toBeNull();
        expect(screen.getByRole('columnheader', { name: 'Gain %' })).toBeInTheDocument();
    });
});
