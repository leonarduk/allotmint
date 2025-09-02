import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import ValueAtRisk from "./ValueAtRisk";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ValueAtRisk component", () => {
  it("renders VaR values and selectors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        owner: "alice",
        as_of: "2024-01-01",
        var: { "1d": 123.45, "10d": 678.9 },
      }),
    } as unknown as Response);

    render(<ValueAtRisk owner="alice" />);

    await waitFor(() => screen.getByText(/95%:/));

    expect(screen.getByText(/95%:/)).toHaveTextContent("£123.45");
    expect(screen.getByText(/99%:/)).toHaveTextContent("£678.90");

    const periodSel = screen.getByLabelText(/Period/i);
    fireEvent.change(periodSel, { target: { value: "90" } });

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(2));
  });

  it("renders placeholder when data missing and triggers recomputation", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          owner: "alice",
          as_of: "2024-01-01",
          var: { "1d": null, "10d": null },
        }),
      } as unknown as Response)
      .mockResolvedValue({
        ok: true,
        json: async () => ({ owner: "alice", var: { "1d": 1, "10d": 2 } }),
      } as unknown as Response);

    render(<ValueAtRisk owner="alice" />);

    await waitFor(() =>
      screen.getByText(/No VaR data available\./i)
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it("skips state updates when unmounted", async () => {
    let resolveFetch!: (value: Response) => void;
    const fetchPromise = new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(() => fetchPromise as unknown as Promise<Response>);

    const { unmount } = render(<ValueAtRisk owner="alice" />);
    unmount();
    resolveFetch({
      ok: true,
      json: async () => ({ owner: "alice", var: { "1d": 1, "10d": 2 } }),
    } as unknown as Response);

    await fetchPromise;
    expect(fetchMock).toHaveBeenCalled();
  });
});
