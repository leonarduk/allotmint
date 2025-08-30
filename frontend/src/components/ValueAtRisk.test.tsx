import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import ValueAtRisk from "./ValueAtRisk";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ValueAtRisk component", () => {
  it("renders VaR values and selectors", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => [{ date: "2024-01-01", var: 123.45 }],
    } as unknown as Response);

    render(<ValueAtRisk owner="alice" />);

    await waitFor(() => screen.getByText(/95%:/));

    expect(screen.getByText(/95%:/)).toHaveTextContent("£123.45");
    expect(screen.getByText(/99%:/)).toHaveTextContent("£123.45");

    const periodSel = screen.getByLabelText(/Period/i);
    fireEvent.change(periodSel, { target: { value: "90" } });

    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(4));
  });

  it("renders placeholder when data missing and triggers recomputation", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      } as unknown as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      } as unknown as Response)
      .mockResolvedValue({
        ok: true,
        json: async () => ({ owner: "alice", var: {} }),
      } as unknown as Response);

    render(<ValueAtRisk owner="alice" />);

    await waitFor(() =>
      screen.getByText(/No VaR data available\./i)
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
  });
});
