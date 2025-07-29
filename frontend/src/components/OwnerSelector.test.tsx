import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { OwnerSelector } from "./OwnerSelector";

describe("OwnerSelector", () => {
  it("renders and triggers callback on change", () => {
    const mockOnSelect = vi.fn();
    const mockOwners = [
      { owner: "alice", accounts: ["ISA", "SIPP"] },
      { owner: "bob", accounts: ["ISA"] },
    ];

    render(
      <OwnerSelector
        owners={mockOwners}
        selected="alice"
        onSelect={mockOnSelect}
      />
    );

    const select = screen.getByRole("combobox");
    fireEvent.change(select, { target: { value: "bob" } });

    expect(mockOnSelect).toHaveBeenCalledWith("bob");
  });
});
