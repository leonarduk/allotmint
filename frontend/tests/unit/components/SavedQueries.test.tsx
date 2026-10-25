import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import "@testing-library/jest-dom/vitest";
// Side-effect import: initializes the global i18next instance so
// useTranslation() inside SavedQueries resolves without wrapping every
// render in an I18nextProvider (same pattern as HoldingsTable.test.tsx).
import "@/i18n";

vi.mock("@/api", () => ({
  listSavedQueries: vi.fn(),
}));

import { listSavedQueries } from "@/api";
import { SavedQueries } from "@/components/SavedQueries";

describe("SavedQueries", () => {
  beforeEach(() => {
    vi.resetAllMocks();
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
