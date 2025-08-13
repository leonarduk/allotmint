import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("../api", () => ({
  API_BASE: "http://api",
  getOwners: vi.fn().mockResolvedValue([
    { owner: "Alice", accounts: [] },
    { owner: "Bob", accounts: [] },
  ]),
  runCustomQuery: vi.fn().mockResolvedValue([
    { owner: "Alice", ticker: "AAA", price: 100 },
  ]),
  saveCustomQuery: vi.fn().mockResolvedValue({}),
  listSavedQueries: vi.fn().mockResolvedValue([
    {
      id: "1",
      name: "Saved1",
      params: {
        start: "2024-01-01",
        end: "2024-01-31",
        owners: ["Bob"],
        tickers: ["BBB"],
        metrics: ["price"],
        granularity: "weekly",
      },
    },
  ]),
}));

import { runCustomQuery } from "../api";
import { QueryPage } from "./QueryPage";

describe("QueryPage", () => {
  it("submits form and renders results with export links", async () => {
    render(<QueryPage />);

    await screen.findByLabelText("Alice");

    fireEvent.change(screen.getByLabelText(/Start/), {
      target: { value: "2024-01-01" },
    });
    fireEvent.change(screen.getByLabelText(/End/), {
      target: { value: "2024-02-01" },
    });

    fireEvent.click(screen.getByLabelText("Alice"));
    fireEvent.click(screen.getByLabelText("AAA"));
    fireEvent.change(screen.getByLabelText("Granularity"), {
      target: { value: "weekly" },
    });
    fireEvent.click(screen.getByLabelText("price"));

    fireEvent.click(screen.getByRole("button", { name: /run/i }));

    expect(runCustomQuery).toHaveBeenCalledWith({
      start: "2024-01-01",
      end: "2024-02-01",
      owners: ["Alice"],
      tickers: ["AAA"],
      metrics: ["price"],
      granularity: "weekly",
    });

    expect(await screen.findByText("AAA")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /csv/i })).toHaveAttribute(
      "href",
      expect.stringContaining("format=csv"),
    );
    expect(screen.getByRole("link", { name: /xlsx/i })).toHaveAttribute(
      "href",
      expect.stringContaining("format=xlsx"),
    );
  });

  it("loads saved queries into the form", async () => {
    render(<QueryPage />);
    const btn = await screen.findByText("Saved1");
    fireEvent.click(btn);
    expect(screen.getByLabelText(/Start/)).toHaveValue("2024-01-01");
    expect(screen.getByLabelText("Granularity")).toHaveValue("weekly");
  });
});
