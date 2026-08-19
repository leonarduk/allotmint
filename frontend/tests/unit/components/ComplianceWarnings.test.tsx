import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { ComplianceWarnings } from "@/components/ComplianceWarnings";
import { getCompliance } from "@/api";
import { useConfig } from "@/ConfigContext";

vi.mock("@/api", () => ({
    getCompliance: vi.fn(),
}));

vi.mock("@/ConfigContext", () => ({
    useConfig: vi.fn(),
}));

beforeEach(() => {
    vi.clearAllMocks();
});

function mockComplianceTab(enabled: boolean) {
    (useConfig as unknown as Mock).mockReturnValue({
        tabs: { "trade-compliance": enabled },
        disabledTabs: enabled ? [] : ["trade-compliance"],
    });
}

describe("ComplianceWarnings", () => {
    it("does not render when there are no warnings", async () => {
        mockComplianceTab(true);
        const mock = getCompliance as unknown as Mock;
        mock.mockResolvedValue({ owner: "alice", warnings: [], trade_counts: {} });

        render(<ComplianceWarnings owners={["alice"]} />);

        await waitFor(() => {
            expect(mock).toHaveBeenCalled();
        });

        expect(screen.queryByText("alice")).not.toBeInTheDocument();
    });

    it("renders warnings when present", async () => {
        mockComplianceTab(true);
        const mock = getCompliance as unknown as Mock;
        mock.mockResolvedValue({ owner: "alice", warnings: ["Issue"], trade_counts: {} });

        render(<ComplianceWarnings owners={["alice"]} />);

        await screen.findByText("Issue");
    });

    it("only shows owners with warnings", async () => {
        mockComplianceTab(true);
        const mock = getCompliance as unknown as Mock;
        mock
            .mockResolvedValueOnce({ owner: "alice", warnings: [], trade_counts: {} })
            .mockResolvedValueOnce({ owner: "bob", warnings: ["Issue"], trade_counts: {} });

        render(<ComplianceWarnings owners={["alice", "bob"]} />);

        await screen.findByText("Issue");
        await waitFor(() =>
            expect(screen.queryByText("alice")).not.toBeInTheDocument(),
        );
        expect(screen.getByText("bob")).toBeInTheDocument();
    });

    it("does not fetch or render when the trade-compliance tab is disabled", async () => {
        mockComplianceTab(false);
        const mock = getCompliance as unknown as Mock;
        mock.mockResolvedValue({ owner: "alice", warnings: ["Issue"], trade_counts: {} });

        render(<ComplianceWarnings owners={["alice"]} />);

        expect(mock).not.toHaveBeenCalled();
        expect(screen.queryByText("Issue")).not.toBeInTheDocument();
    });

    it("drops an owner instead of showing a fake warning when the fetch fails (e.g. a 402)", async () => {
        mockComplianceTab(true);
        const mock = getCompliance as unknown as Mock;
        mock.mockRejectedValue(new Error("402 Payment Required"));

        render(<ComplianceWarnings owners={["alice"]} />);

        await waitFor(() => {
            expect(mock).toHaveBeenCalled();
        });

        expect(screen.queryByText("Failed to load warnings")).not.toBeInTheDocument();
        expect(screen.queryByText("alice")).not.toBeInTheDocument();
    });
});
