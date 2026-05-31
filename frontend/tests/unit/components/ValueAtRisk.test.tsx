import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import ValueAtRisk from "@/components/ValueAtRisk";

// Mock the api module directly to avoid depending on globalThis.fetch
// indirection through dynamicFetch, which can be timing-sensitive in CI.
vi.mock("@/api", () => ({
  getValueAtRisk: vi.fn(),
  recomputeValueAtRisk: vi.fn(),
  getVarBreakdown: vi.fn(),
}));

import * as api from "@/api";

afterEach(() => {
  vi.clearAllMocks();
});

describe("ValueAtRisk component", () => {
  it("renders VaR values and selectors", async () => {
    vi.mocked(api.getValueAtRisk).mockResolvedValue({
      owner: "alice",
      as_of: "2024-01-01",
      var: { "1d": 123.45, "10d": 678.9 },
    } as any);

    render(<ValueAtRisk owner="alice" />);

    await waitFor(() => screen.getByText(/95%:/));

    expect(screen.getByText(/95%:/)).toHaveTextContent("£123.45");
    expect(screen.getByText(/99%:/)).toHaveTextContent("£678.90");

    const periodSel = screen.getByLabelText(/Period/i);
    fireEvent.change(periodSel, { target: { value: "90" } });

    await waitFor(() =>
      expect(api.getValueAtRisk).toHaveBeenCalledTimes(2)
    );
    expect(api.getValueAtRisk).toHaveBeenLastCalledWith("alice", { days: 90 });
  });

  it("opens breakdown modal when VaR value clicked", async () => {
    const onDateChange = vi.fn();
    vi.mocked(api.getValueAtRisk).mockResolvedValue({
      owner: "alice",
      as_of: "2024-01-01",
      var: { "1d": 100, "10d": 200 },
    } as any);
    vi.mocked(api.getVarBreakdown).mockResolvedValue({
      varDate: "2024-01-02",
      varLossPercent: 5.0,
      scenarios: [
        { date: "2024-01-02", portfolio_return: -0.05, loss_percent: 5.0 },
      ],
      breakdown: [
        { ticker: "AAA", name: "Alpha Plc", relative_change_percent: -12.5, scenario_amount_gbp: -75, contribution: 60 },
        { ticker: "BBB", name: "Beta Ltd", relative_change_percent: 8.4, scenario_amount_gbp: 20, contribution: 40 },
      ],
    } as any);

    render(<ValueAtRisk owner="alice" onDateChange={onDateChange} />);

    await waitFor(() =>
      expect(screen.getByText(/95%:/)).toHaveTextContent("£100.00")
    );

    const btn = screen.getAllByRole("button")[0];
    fireEvent.click(btn);

    await waitFor(() => screen.getByRole("dialog"));
    expect(screen.getByRole("dialog")).toHaveTextContent("VaR quantile date: 2024-01-02");
    expect(screen.getByRole("dialog")).toHaveTextContent("AAA");
    expect(screen.getByRole("dialog")).toHaveTextContent("BBB");
    expect(screen.getByRole("dialog")).toHaveTextContent("Alpha Plc");
    expect(screen.getByRole("dialog")).toHaveTextContent("-12.50%");
    expect(screen.getByRole("dialog")).toHaveTextContent("+8.40%");
    expect(screen.getByRole("dialog")).toHaveTextContent("-75.00");
    expect(screen.getByRole("dialog")).toHaveTextContent("+20.00");
    expect(screen.getByRole("dialog")).toHaveTextContent("2024-01-02");
    fireEvent.keyDown(document.body, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    fireEvent.click(btn);
    await waitFor(() => screen.getByRole("dialog"));
    fireEvent.click(screen.getByRole("button", { name: /Show report/i }));
    expect(onDateChange).toHaveBeenCalledWith("2024-01-02");
  });

  it("renders placeholder when data missing and triggers recomputation", async () => {
    vi.mocked(api.getValueAtRisk)
      .mockResolvedValueOnce({
        owner: "alice",
        as_of: "2024-01-01",
        var: { "1d": null, "10d": null },
      } as any)
      .mockResolvedValue({
        owner: "alice",
        var: { "1d": 1, "10d": 2 },
      } as any);
    vi.mocked(api.recomputeValueAtRisk).mockResolvedValue(undefined as any);

    render(<ValueAtRisk owner="alice" />);

    await waitFor(() =>
      screen.getByText(/No VaR data available\./i)
    );

    await waitFor(() => expect(api.recomputeValueAtRisk).toHaveBeenCalledTimes(1));
    // After recompute, the component should not re-fetch automatically
    // (recompute is fire-and-forget; a page refresh or period change triggers the next fetch).
    expect(api.getValueAtRisk).toHaveBeenCalledTimes(1);
  });

  it("skips state updates when unmounted", async () => {
    let resolve!: (value: any) => void;
    const pending = new Promise<any>((res) => { resolve = res; });
    vi.mocked(api.getValueAtRisk).mockImplementation(() => pending);

    const { unmount } = render(<ValueAtRisk owner="alice" />);
    unmount();
    resolve({ owner: "alice", var: { "1d": 1, "10d": 2 } });

    await pending;
    expect(api.getValueAtRisk).toHaveBeenCalled();
  });
});
