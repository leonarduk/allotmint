import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("../api", () => ({
  getOwners: vi.fn(),
  API_BASE: "http://test",
}));

import Reports from "./Reports";
import { getOwners } from "../api";

describe("Reports page", () => {
  it("shows links when owner selected", async () => {
    (getOwners as ReturnType<typeof vi.fn>).mockResolvedValue([
      { owner: "alex", accounts: [] },
    ]);

    render(<Reports />);

    const select = await screen.findByLabelText(/owner/i);
    fireEvent.change(select, { target: { value: "alex" } });

    const csv = await screen.findByText(/Download CSV/i);
    expect(csv).toHaveAttribute("href", expect.stringContaining("/reports/alex"));
  });
});

