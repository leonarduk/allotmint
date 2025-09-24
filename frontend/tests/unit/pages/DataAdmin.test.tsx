import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

vi.mock("@/api", () => ({
  listTimeseries: vi.fn().mockResolvedValue([
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
  ]),
  refetchTimeseries: vi.fn().mockResolvedValue({ status: "ok", rows: 1 }),
  rebuildTimeseriesCache: vi.fn().mockResolvedValue({ status: "ok", rows: 1 }),
}));

import DataAdmin from "@/pages/DataAdmin";

describe("DataAdmin page", () => {
  it("renders table, actions, and ticker link", async () => {
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
});
