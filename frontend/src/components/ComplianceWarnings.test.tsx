import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, type Mock } from "vitest";
import { ComplianceWarnings } from "./ComplianceWarnings";
import { getCompliance } from "../api";

vi.mock("../api", () => ({
    getCompliance: vi.fn(),
}));

describe("ComplianceWarnings", () => {
    it("does not render when there are no warnings", async () => {
        const mock = getCompliance as unknown as Mock;
        mock.mockResolvedValue({ owner: "alice", warnings: [], trade_counts: {} });

        render(<ComplianceWarnings owners={["alice"]} />);

        await waitFor(() => {
            expect(mock).toHaveBeenCalled();
        });

        expect(screen.queryByText("alice")).not.toBeInTheDocument();
    });

    it("renders warnings when present", async () => {
        const mock = getCompliance as unknown as Mock;
        mock.mockResolvedValue({ owner: "alice", warnings: ["Issue"], trade_counts: {} });

        render(<ComplianceWarnings owners={["alice"]} />);

        await screen.findByText("Issue");
    });

    it("only shows owners with warnings", async () => {
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

});
