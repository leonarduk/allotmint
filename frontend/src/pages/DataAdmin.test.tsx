import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("../api", () => ({
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
}));

import DataAdmin from "./DataAdmin";

describe("DataAdmin page", () => {
  it("renders table and ticker links to edit page", async () => {
    render(<DataAdmin />);
    const link = await screen.findByRole("link", { name: "ABC" });
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(link).toHaveAttribute(
      "href",
      "/timeseries?ticker=ABC&exchange=L",
    );
  });
});
