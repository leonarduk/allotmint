import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import "@testing-library/jest-dom/vitest";

vi.mock("@/api", () => ({
  listSavedQueries: vi.fn(),
}));

import { listSavedQueries } from "@/api";
import { SavedQueries } from "@/components/SavedQueries";

describe("SavedQueries", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  // Issue #7202: the backend's `/custom-query/saved` listing surfaces the
  // developer-seeded `data/queries/demo-slug.json` example indistinguishably
  // from a real saved query. It should never render in the user-facing list.
  it("hides the seeded demo-slug example query", async () => {
    listSavedQueries.mockResolvedValue([
      {
        id: "demo-slug",
        name: "demo-slug",
        params: { tickers: ["PFE"], metrics: [] },
      },
      {
        id: "real-query",
        name: "My real query",
        params: { tickers: ["VOD"], metrics: [] },
      },
    ]);
    const onLoad = vi.fn();
    render(<SavedQueries onLoad={onLoad} />);

    expect(await screen.findByText("My real query")).toBeInTheDocument();
    expect(screen.queryByText("demo-slug")).not.toBeInTheDocument();
  });

  it("loads a real saved query's params on click", async () => {
    listSavedQueries.mockResolvedValue([
      {
        id: "real-query",
        name: "My real query",
        params: { tickers: ["VOD"], metrics: [] },
      },
    ]);
    const onLoad = vi.fn();
    render(<SavedQueries onLoad={onLoad} />);

    fireEvent.click(await screen.findByText("My real query"));
    expect(onLoad).toHaveBeenCalledWith({ tickers: ["VOD"], metrics: [] });
  });
});
