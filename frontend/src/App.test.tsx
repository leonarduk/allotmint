import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";

// Dynamic import after setting location and mocking APIs

describe("App", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("renders timeseries editor when path is /portfolio/timeseries", async () => {
    window.history.pushState({}, "", "/portfolio/timeseries?ticker=ABC&exchange=L");

    vi.mock("./api", () => ({
      getOwners: vi.fn().mockResolvedValue([]),
      getGroups: vi.fn().mockResolvedValue([]),
      getGroupInstruments: vi.fn().mockResolvedValue([]),
      getPortfolio: vi.fn(),
      refreshPrices: vi.fn(),
      getAlerts: vi.fn().mockResolvedValue([]),
      getCompliance: vi.fn().mockResolvedValue({ owner: "", warnings: [] }),
      getTimeseries: vi.fn().mockResolvedValue([]),
      saveTimeseries: vi.fn(),
    }));

    const { default: App } = await import("./App");

    render(
      <MemoryRouter
        initialEntries={["/portfolio/timeseries?ticker=ABC&exchange=L"]}
      >
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Timeseries Editor")).toBeInTheDocument();
  });
});
