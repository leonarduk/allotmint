import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

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
    mockListTimeseries.mockRejectedValue(
      new Error(
        "No local login override is configured. Go to Support -> Local login override and select a user to continue in local/demo mode.",
      ),
    );

    render(
      <MemoryRouter>
        <DataAdmin />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No local login override is configured",
    );
    expect(
      screen.getByRole("link", { name: "Configure local login override" }),
    ).toHaveAttribute("href", "/support#local-login-override");
  });
});
