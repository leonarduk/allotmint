import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { GroupSelector } from "./GroupSelector";

describe("GroupSelector", () => {
  it("renders and triggers callback on change", () => {
    const mockOnSelect = vi.fn();
    const mockGroups = [
      { slug: "family", members: ["steve", "lucy"] },
      { slug: "kids", members: ["alex", "joe"] },
    ];

    render(
      <GroupSelector
        groups={mockGroups}
        selected="family"
        onSelect={mockOnSelect}
      />
    );

    const select = screen.getByRole("combobox");
    fireEvent.change(select, { target: { value: "kids" } });

    expect(mockOnSelect).toHaveBeenCalledWith("kids");
  });
});
