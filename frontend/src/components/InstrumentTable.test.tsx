import { render, screen, fireEvent } from "@testing-library/react";
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
            units: 10,
            market_value_gbp: 1000,
            gain_gbp: 100,
            last_price_gbp: 100,
            last_price_date: "2024-01-01",
            change_7d_pct: 1,
            change_30d_pct: 2,
        },
    ];

    it("passes ticker and name to InstrumentDetail", () => {
        render(<InstrumentTable rows={rows} />);
        fireEvent.click(screen.getByText("ABC"));

        const mock = InstrumentDetail as unknown as Mock;
        expect(mock).toHaveBeenCalled();
        const props = mock.mock.calls[0][0] as any;
        expect(props.ticker).toBe("ABC");
        expect(props.name).toBe("ABC Corp");
    });
});
