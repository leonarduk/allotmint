import { beforeEach, describe, expect, it } from "vitest";
import {
  DEFAULT_WATCHLIST_SYMBOLS,
  LEGACY_WATCHLIST_STORAGE_KEY,
  WATCHLISTS_STORAGE_KEY,
  copyWatchlist,
  createWatchlist,
  deleteWatchlist,
  readActiveSymbols,
  readWatchlists,
  renameWatchlist,
  setWatchlistSymbols,
  suggestCopyName,
} from "@/lib/watchlistStore";

describe("watchlistStore", () => {
  beforeEach(() => localStorage.clear());

  it("shows the default symbols as one list when nothing is stored", () => {
    const state = readWatchlists();
    expect(state.lists).toHaveLength(1);
    expect(state.lists[0].name).toBe("My watchlist");
    expect(state.lists[0].symbols.join(",")).toBe(DEFAULT_WATCHLIST_SYMBOLS);
  });

  it("migrates the legacy single list and leaves the legacy key in place", () => {
    localStorage.setItem(LEGACY_WATCHLIST_STORAGE_KEY, "AAA, BBB");
    createWatchlist("Second");

    const state = readWatchlists();
    expect(state.lists.map((l) => l.name)).toEqual(["My watchlist", "Second"]);
    expect(state.lists[0].symbols).toEqual(["AAA", "BBB"]);
    expect(localStorage.getItem(LEGACY_WATCHLIST_STORAGE_KEY)).toBe("AAA, BBB");
  });

  it("falls back to the legacy list when stored JSON is unreadable", () => {
    localStorage.setItem(LEGACY_WATCHLIST_STORAGE_KEY, "AAA");
    localStorage.setItem(WATCHLISTS_STORAGE_KEY, "{not json");
    expect(readActiveSymbols()).toEqual(["AAA"]);
  });

  it("drops malformed lists and repairs a dangling activeId", () => {
    localStorage.setItem(
      WATCHLISTS_STORAGE_KEY,
      JSON.stringify({
        activeId: "gone",
        lists: [{ id: "x" }, { id: "ok", name: "Ok", symbols: ["Z"] }],
      }),
    );
    const state = readWatchlists();
    expect(state.lists.map((l) => l.id)).toEqual(["ok"]);
    expect(state.activeId).toBe("ok");
  });

  it("rejects blank and case-insensitive duplicate names", () => {
    expect(createWatchlist("   ")).toBeNull();
    expect(createWatchlist("MY WATCHLIST")).toBeNull();
    const id = createWatchlist("Other")!;
    expect(renameWatchlist(id, "my watchlist")).toBe(false);
    expect(renameWatchlist(id, "other")).toBe(true);
  });

  it("copies symbols independently of the source", () => {
    localStorage.setItem(LEGACY_WATCHLIST_STORAGE_KEY, "AAA");
    const sourceId = readWatchlists().lists[0].id;
    const copyId = copyWatchlist(sourceId, "Copy")!;
    setWatchlistSymbols(copyId, ["BBB"]);

    const byId = Object.fromEntries(
      readWatchlists().lists.map((l) => [l.id, l.symbols]),
    );
    expect(byId[sourceId]).toEqual(["AAA"]);
    expect(byId[copyId]).toEqual(["BBB"]);
  });

  it("never deletes the last list, and re-targets active on delete", () => {
    const first = readWatchlists().lists[0].id;
    expect(deleteWatchlist(first)).toBe(false);

    const second = createWatchlist("Second")!;
    expect(readWatchlists().activeId).toBe(second);
    expect(deleteWatchlist(second)).toBe(true);
    expect(readWatchlists().activeId).toBe(first);
  });

  it("suggests a free copy name", () => {
    createWatchlist("My watchlist (copy)");
    expect(suggestCopyName(readWatchlists(), "My watchlist")).toBe(
      "My watchlist (copy 2)",
    );
  });
});
