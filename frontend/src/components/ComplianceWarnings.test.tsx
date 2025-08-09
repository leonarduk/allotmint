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
        mock.mockResolvedValue({ warnings: [] });

        render(<ComplianceWarnings owners={["alice"]} />);

        await waitFor(() => {
            expect(mock).toHaveBeenCalled();
        });

        expect(screen.queryByText("alice")).not.toBeInTheDocument();
    });

    it("renders warnings when present", async () => {
        const mock = getCompliance as unknown as Mock;
        mock.mockResolvedValue({ warnings: ["Issue"] });

        render(<ComplianceWarnings owners={["alice"]} />);

        await screen.findByText("Issue");
    });

    it("only shows owners with warnings", async () => {
        const mock = getCompliance as unknown as Mock;
        mock
            .mockResolvedValueOnce({ warnings: [] })
            .mockResolvedValueOnce({ warnings: ["Issue"] });

        render(<ComplianceWarnings owners={["alice", "bob"]} />);

        await screen.findByText("Issue");
        expect(screen.queryByText("alice")).not.toBeInTheDocument();
        expect(screen.getByText("bob")).toBeInTheDocument();
    });

});
