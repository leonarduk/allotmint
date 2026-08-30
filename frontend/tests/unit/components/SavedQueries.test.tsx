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

  // Issue #7222/#7202: the developer-seeded `data/queries/demo-slug.json`
  // fixture used to leak into the user-facing "saved queries" list. That's
  // now fixed server-side — GET /custom-query/saved excludes seeded fixture
  // slugs before this component ever sees them (see
  // backend/routes/query.py::list_saved_queries and its regression coverage
  // in tests/backend/test_custom_query_route.py) — so this component can
  // trust every entry it receives is a real saved query and doesn't need its
  // own blocklist.
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
