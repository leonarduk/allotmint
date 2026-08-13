import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";

const mockListTimeseries = vi.hoisted(() => vi.fn());

vi.mock("@/api", () => ({
  listTimeseries: mockListTimeseries,
  refetchTimeseries: vi.fn().mockResolvedValue({ status: "ok", rows: 1 }),
  rebuildTimeseriesCache: vi.fn().mockResolvedValue({ status: "ok", rows: 1 }),
}));

const timeseriesRows = [
    {
      ticker: "ABC",
      exchange: "L",
      name: "ABC plc",
      earliest: "2024-01-01",
      latest: "2024-02-01",
      completeness: 100,
      latest_source: "Feed",
      main_source: "Feed",
    },
  ];

import DataAdmin from "@/pages/DataAdmin";

describe("DataAdmin page", () => {
  it("renders table, actions, and ticker link", async () => {
    mockListTimeseries.mockResolvedValue(timeseriesRows);
    render(
      <MemoryRouter>
        <DataAdmin />
      </MemoryRouter>,
    );
    const link = await screen.findByRole("link", { name: "ABC" });
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(link).toHaveAttribute(
      "href",
      "/timeseries?ticker=ABC&exchange=L",
    );
    expect(await screen.findByRole("button", { name: "Refetch" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rebuild cache" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open instrument" })).toBeInTheDocument();
  });

  it("links a missing local login error to the relevant support control", async () => {
    const user = userEvent.setup();
    mockListTimeseries.mockRejectedValue(
      new Error(
        "No local login override is configured. Go to Support -> Local login override and select a user to continue in local/demo mode.",
      ),
    );

    const LocationDisplay = () => {
      const location = useLocation();
      return (
        <div data-testid="location-display">
          {location.pathname}
          {location.hash}
        </div>
      );
    };

    render(
      <MemoryRouter initialEntries={["/dataadmin"]}>
        <DataAdmin />
        <LocationDisplay />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No local login override is configured",
    );
    const link = screen.getByRole("link", {
      name: "Configure local login override",
    });
    expect(link).toHaveAttribute("href", "/support#local-login-override");

    await user.click(link);

    expect(screen.getByTestId("location-display")).toHaveTextContent(
      "/support#local-login-override",
    );
  });
});
