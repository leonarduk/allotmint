import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { CriteriaBuilder, Criterion } from "./CriteriaBuilder";

describe("CriteriaBuilder", () => {
  it("adds a new criterion", () => {
    const handleChange = vi.fn();
    render(<CriteriaBuilder criteria={[]} onChange={handleChange} />);
    fireEvent.click(screen.getByText("Add"));
    expect(handleChange).toHaveBeenCalledWith([
      { field: "", operator: "", value: "" },
    ]);
  });

  it("updates an existing criterion", () => {
    const initial: Criterion[] = [{ field: "", operator: "", value: "" }];
    const handleChange = vi.fn();
    render(<CriteriaBuilder criteria={initial} onChange={handleChange} />);
    fireEvent.change(screen.getByLabelText("field-0"), {
      target: { value: "peg_ratio" },
    });
    expect(handleChange).toHaveBeenCalledWith([
      { field: "peg_ratio", operator: "", value: "" },
    ]);
  });

  it("removes a criterion", () => {
    const initial: Criterion[] = [{ field: "", operator: "", value: "" }];
    const handleChange = vi.fn();
    render(<CriteriaBuilder criteria={initial} onChange={handleChange} />);
    fireEvent.click(screen.getByLabelText("remove-0"));
    expect(handleChange).toHaveBeenCalledWith([]);
  });
});
