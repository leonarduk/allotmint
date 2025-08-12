import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("../api", () => ({
  API_BASE: "",
  getConfig: vi.fn().mockResolvedValue({ flag: true }),
  updateConfig: vi.fn(),
}));

import Support from "./Support";

describe("Support page", () => {
  it("renders environment heading", () => {
    render(<Support />);
    expect(screen.getByText(/Environment/)).toBeInTheDocument();
  });

  it("shows swagger link for VITE_API_URL", () => {
    vi.stubEnv("VITE_API_URL", "http://localhost:8000");
    render(<Support />);
    expect(
      screen.getByRole("link", { name: "http://localhost:8000" })
    ).toHaveAttribute("href", "http://localhost:8000");
    expect(screen.getByRole("link", { name: "swagger" })).toHaveAttribute(
      "href",
      "http://localhost:8000/docs#/"
    );
    vi.unstubAllEnvs();
  });
});
