import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Discover } from "./Discover";

describe("Discover page", () => {
  it("renders heading and allows adding criteria", () => {
    render(<Discover />);
    expect(screen.getByText("Discover")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Add"));
    expect(screen.getByLabelText("field-0")).toBeInTheDocument();
  });
});
