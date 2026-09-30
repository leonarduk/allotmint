import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as api from "@/api";
import { DeleteSeriesButton } from "@/components/DeleteSeriesButton";

const refs = (overrides: Partial<api.SeriesReferences> = {}): api.SeriesReferences => ({
  ticker: "IONQ",
  exchange: "L",
  exists: true,
  references: [],
  has_metadata: false,
  orphaned: true,
  can_delete: true,
  ...overrides,
});

afterEach(() => vi.restoreAllMocks());

describe("DeleteSeriesButton", () => {
  it("is hidden when the series cannot be deleted", async () => {
    const spy = vi.spyOn(api, "getSeriesReferences").mockResolvedValue(refs({ can_delete: false }));
    render(<DeleteSeriesButton ticker="IONQ" exchange="N" />);
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "Delete Series" })).toBeNull();
  });

  it("does nothing when the confirmation is cancelled", async () => {
    vi.spyOn(api, "getSeriesReferences").mockResolvedValue(refs());
    const del = vi.spyOn(api, "deleteTimeseries");
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<DeleteSeriesButton ticker="IONQ" exchange="L" />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete Series" }));
    expect(del).not.toHaveBeenCalled();
  });

  it("deletes after confirmation and hides the button", async () => {
    vi.spyOn(api, "getSeriesReferences").mockResolvedValue(refs());
    const del = vi.spyOn(api, "deleteTimeseries").mockResolvedValue({ status: "ok", rows: 3, ticker: "IONQ", exchange: "L" });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const onDeleted = vi.fn();
    render(<DeleteSeriesButton ticker="IONQ" exchange="L" onDeleted={onDeleted} />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete Series" }));
    expect(del).toHaveBeenCalledWith("IONQ", "L");
    expect(await screen.findByRole("status")).toHaveTextContent("Deleted series IONQ.L.");
    expect(screen.queryByRole("button", { name: "Delete Series" })).toBeNull();
    expect(onDeleted).toHaveBeenCalled();
  });

  it("shows the backend refusal message", async () => {
    vi.spyOn(api, "getSeriesReferences").mockResolvedValue(refs());
    vi.spyOn(api, "deleteTimeseries").mockRejectedValue(new Error("Cannot delete IONQ.L: still referenced by holding in alice/isa"));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<DeleteSeriesButton ticker="IONQ" exchange="L" />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete Series" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("still referenced by holding in alice/isa");
  });
});
