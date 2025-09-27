import {fireEvent, render, screen} from "@testing-library/react";
import {describe, expect, it, vi} from "vitest";
import {OwnerSelector} from "@/components/OwnerSelector";

describe("OwnerSelector", () => {
    it("renders and triggers callback on change", () => {
        const mockOnSelect = vi.fn();
        const mockOwners = [
            {owner: "alice", full_name: "Alice Example", accounts: ["ISA", "SIPP"]},
            {owner: "bob", full_name: "Bob Example", accounts: ["ISA"]},
        ];

        render(
            <OwnerSelector
                owners={mockOwners}
                selected="alice"
                onSelect={mockOnSelect}
            />
        );

        const select = screen.getByRole("combobox");
        expect(screen.getByRole("option", { name: "Alice Example" })).toBeInTheDocument();
        fireEvent.change(select, {target: {value: "bob"}});

        expect(mockOnSelect).toHaveBeenCalledWith("bob");
    });
});
