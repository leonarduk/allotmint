import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

// Dynamic import after setting location and mocking APIs

describe("App", () => {
  it("preselects group from URL", async () => {
    window.history.pushState({}, "", "/instrument/kids");

    vi.mock("./api", () => ({
      getOwners: vi.fn().mockResolvedValue([]),
      getGroups: vi.fn().mockResolvedValue([
        { slug: "family", name: "Family", members: [] },
        { slug: "kids", name: "Kids", members: [] },
      ]),
      getGroupInstruments: vi.fn().mockResolvedValue([]),
      getPortfolio: vi.fn(),
      refreshPrices: vi.fn(),
      getAlerts: vi.fn().mockResolvedValue([]),
      getCompliance: vi.fn().mockResolvedValue({ owner: "", warnings: [] }),
    }));

    const { default: App } = await import("./App");

    render(
      <BrowserRouter>
        <App />
      </BrowserRouter>
    );

    const select = await screen.findByRole("combobox");
    expect(select).toHaveValue("kids");
  });
});
