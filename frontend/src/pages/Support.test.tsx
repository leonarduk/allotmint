import { render, screen } from "@testing-library/react";
import Support from "./Support";

describe("Support page", () => {
  it("renders environment heading", () => {
    render(<Support />);
    expect(screen.getByText(/Environment/)).toBeInTheDocument();
  });
});
