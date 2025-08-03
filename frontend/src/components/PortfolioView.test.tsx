import {render, screen} from "@testing-library/react";
import {PortfolioView} from "./PortfolioView";
import type {Portfolio} from "../types";

describe("PortfolioView", () => {
    const mockOwner: Portfolio = {
        owner: "steve",
        as_of: "2025-07-29",
        trades_this_month: 0,
        trades_remaining: 20,
        total_value_estimate_gbp: 14925,
        accounts: [
            {
                account_type: "ISA",
                currency: "GBP",
                value_estimate_gbp: 0,
                last_updated: "2025-07-24",
                holdings: [],
            },
            {
                account_type: "SIPP",
                currency: "GBP",
                value_estimate_gbp: 14925,
                last_updated: "2025-07-15",
                holdings: [],
            },
        ],
    };

    it("renders owner's name and account blocks", () => {
        render(<PortfolioView data={mockOwner}/>);
        expect(screen.getByTestId("owner-name")).toHaveTextContent("steve");

        // Match headings like "ISA (GBP)"
        const isaBlock = screen.getByText((_, el) => {
            if (!el) return false;
            const isHeading = el.tagName.toLowerCase() === "h2";
            const startsWithIsa = el.textContent?.trim().startsWith("ISA") ?? false;
            return isHeading && startsWithIsa;
        });

        expect(isaBlock).toBeInTheDocument();

        expect(screen.getByText(/SIPP.*GBP/)).toBeInTheDocument();

    });
});
