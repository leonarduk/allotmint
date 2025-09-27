import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { PortfolioView } from "@/components/PortfolioView";
import type { Portfolio } from "@/types";

vi.mock("@/components/PerformanceDashboard", () => ({
  __esModule: true,
  default: () => <div data-testid="performance-dashboard" />,
}));

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

    it("renders account blocks", () => {
        render(<PortfolioView data={mockOwner}/>);

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

    it("updates total when accounts are toggled", () => {
        render(<PortfolioView data={mockOwner}/>);

        const total = screen.getByText(/Approx Total:/);
        expect(total).toHaveTextContent("£14,925.00");

        const sippCheckbox = screen.getByRole("checkbox", {name: /sipp/i});
        fireEvent.click(sippCheckbox);

        expect(total).toHaveTextContent("£0.00");
    });
});
