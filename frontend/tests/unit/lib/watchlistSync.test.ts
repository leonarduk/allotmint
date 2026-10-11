import { afterEach, beforeEach, describe, expect, it, vi, Mock } from "vitest";
import * as api from "@/api";
import { emitAuthChange } from "@/authEvents";
import { isDemoSession } from "@/demoAuth";
import {
  LEGACY_WATCHLIST_STORAGE_KEY,
  WATCHLISTS_STORAGE_KEY,
  createWatchlist,
  readWatchlists,
  toggleInWatchlist,
  type WatchlistsState,
} from "@/lib/watchlistStore";
import {
  SAVE_DEBOUNCE_MS,
  WATCHLISTS_SYNC_STORAGE_KEY,
  ensureWatchlistsLoaded,
  flush,
  resetWatchlistSyncForTests,
} from "@/lib/watchlistSync";

vi.mock("@/api");
vi.mock("@/demoAuth", () => ({ isDemoSession: vi.fn(() => false) }));

const list = (name: string, symbols: string[], id = "default"): WatchlistsState => ({
  activeId: id,
  lists: [{ id, name, symbols }],
});

const SERVER = list("Server", ["BP.L"]);

function saved(state: WatchlistsState | null, revision = state ? 3 : 0, owner: string | null = "u1") {
  return { owner, revision, state };
}

function sync() {
  return JSON.parse(localStorage.getItem(WATCHLISTS_SYNC_STORAGE_KEY) ?? "null");
}

function conflict(current: { revision: number; state: WatchlistsState | null }) {
  return Object.assign(new Error("conflict"), { status: 409, body: { current } });
}

describe("watchlistSync", () => {
  beforeEach(() => {
    localStorage.clear();
    resetWatchlistSyncForTests();
    vi.clearAllMocks();
    (isDemoSession as Mock).mockReturnValue(false);
    (api.putSavedWatchlists as Mock).mockImplementation(async (state, revision) => ({
      revision: revision + 1,
      state,
    }));
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("adopts the server's copy over a browser that never edited its lists", async () => {
    (api.getSavedWatchlists as Mock).mockResolvedValue(saved(SERVER));

    await ensureWatchlistsLoaded();

    expect(readWatchlists()).toEqual(SERVER);
    expect(sync()).toEqual({ owner: "u1", revision: 3, dirty: false });
    expect(api.putSavedWatchlists).not.toHaveBeenCalled();
  });

  it("uploads this browser's lists once when the server has none", async () => {
    localStorage.setItem(WATCHLISTS_STORAGE_KEY, JSON.stringify(list("Mine", ["AZN.L"])));
    (api.getSavedWatchlists as Mock).mockResolvedValue(saved(null));

    await ensureWatchlistsLoaded();

    expect(api.putSavedWatchlists).toHaveBeenCalledTimes(1);
    expect(api.putSavedWatchlists).toHaveBeenCalledWith(list("Mine", ["AZN.L"]), 0);
    expect(sync()).toEqual({ owner: "u1", revision: 1, dirty: false });
    // Kept for a rollback.
    expect(localStorage.getItem(WATCHLISTS_STORAGE_KEY)).not.toBeNull();
  });

  it("uploads the legacy single list too", async () => {
    localStorage.setItem(LEGACY_WATCHLIST_STORAGE_KEY, "AAA,BBB");
    (api.getSavedWatchlists as Mock).mockResolvedValue(saved(null));

    await ensureWatchlistsLoaded();

    const [state] = (api.putSavedWatchlists as Mock).mock.calls[0];
    expect(state.lists[0].symbols).toEqual(["AAA", "BBB"]);
    expect(localStorage.getItem(LEGACY_WATCHLIST_STORAGE_KEY)).toBe("AAA,BBB");
  });

  it("never uploads the built-in default list from a fresh browser", async () => {
    (api.getSavedWatchlists as Mock).mockResolvedValue(saved(null));

    await ensureWatchlistsLoaded();

    expect(api.putSavedWatchlists).not.toHaveBeenCalled();
    expect(localStorage.getItem(WATCHLISTS_STORAGE_KEY)).toBeNull();
  });

  it("the server's copy wins over a browser's lists on their first sync", async () => {
    localStorage.setItem(WATCHLISTS_STORAGE_KEY, JSON.stringify(list("Mine", ["AZN.L"])));
    (api.getSavedWatchlists as Mock).mockResolvedValue(saved(SERVER));

    await ensureWatchlistsLoaded();

    expect(readWatchlists()).toEqual(SERVER);
    expect(api.putSavedWatchlists).not.toHaveBeenCalled();
  });

  it("replaces a cache that belongs to another user and never uploads it", async () => {
    localStorage.setItem(WATCHLISTS_STORAGE_KEY, JSON.stringify(list("Alice's", ["AZN.L"])));
    localStorage.setItem(
      WATCHLISTS_SYNC_STORAGE_KEY,
      JSON.stringify({ owner: "alice", revision: 4, dirty: true }),
    );
    (api.getSavedWatchlists as Mock).mockResolvedValue(saved(null, 0, "bob"));

    await ensureWatchlistsLoaded();

    expect(api.putSavedWatchlists).not.toHaveBeenCalled();
    expect(readWatchlists().lists.map((l) => l.name)).toEqual(["My watchlist"]);
    expect(sync()).toEqual({ owner: "bob", revision: 0, dirty: false });
  });

  it("saves edits after a debounce, based on the last revision", async () => {
    (api.getSavedWatchlists as Mock).mockResolvedValue(saved(SERVER));
    await ensureWatchlistsLoaded();
    vi.useFakeTimers();

    toggleInWatchlist("default", "VOD.L");
    createWatchlist("Tech");
    expect(api.putSavedWatchlists).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(SAVE_DEBOUNCE_MS);

    expect(api.putSavedWatchlists).toHaveBeenCalledTimes(1);
    const [state, revision] = (api.putSavedWatchlists as Mock).mock.calls[0];
    expect(revision).toBe(3);
    expect(state.lists.map((l: { name: string }) => l.name)).toEqual(["Server", "Tech"]);
    expect(state.lists[0].symbols).toEqual(["BP.L", "VOD.L"]);
    expect(sync()).toEqual({ owner: "u1", revision: 4, dirty: false });
  });

  it("adopts the other device's copy on a conflict", async () => {
    (api.getSavedWatchlists as Mock).mockResolvedValue(saved(SERVER));
    await ensureWatchlistsLoaded();
    const other = list("Other device", ["SHEL.L"]);
    (api.putSavedWatchlists as Mock).mockRejectedValueOnce(conflict({ revision: 5, state: other }));

    toggleInWatchlist("default", "VOD.L");
    await flush();

    expect(readWatchlists()).toEqual(other);
    expect(sync()).toEqual({ owner: "u1", revision: 5, dirty: false });
  });

  it("keeps unsaved edits across a reload and saves them", async () => {
    localStorage.setItem(WATCHLISTS_STORAGE_KEY, JSON.stringify(list("Edited", ["AZN.L"])));
    localStorage.setItem(
      WATCHLISTS_SYNC_STORAGE_KEY,
      JSON.stringify({ owner: "u1", revision: 3, dirty: true }),
    );
    (api.getSavedWatchlists as Mock).mockResolvedValue(saved(SERVER));

    await ensureWatchlistsLoaded();

    expect(api.putSavedWatchlists).toHaveBeenCalledWith(list("Edited", ["AZN.L"]), 3);
    expect(readWatchlists()).toEqual(list("Edited", ["AZN.L"]));
  });

  it("keeps the lists local when the load or a save fails", async () => {
    (api.getSavedWatchlists as Mock).mockRejectedValueOnce(new Error("offline"));
    await ensureWatchlistsLoaded();
    toggleInWatchlist("default", "VOD.L");
    expect(readWatchlists().lists[0].symbols).toContain("VOD.L");

    (api.getSavedWatchlists as Mock).mockResolvedValue(saved(null));
    (api.putSavedWatchlists as Mock).mockRejectedValueOnce(new Error("503"));
    await flush();

    expect(readWatchlists().lists[0].symbols).toContain("VOD.L");
    expect(sync().dirty).toBe(true);
    expect(console.warn).toHaveBeenCalled();
  });

  it("does not sync without an identity", async () => {
    (api.getSavedWatchlists as Mock).mockResolvedValue(saved(null, 0, null));
    await ensureWatchlistsLoaded();

    toggleInWatchlist("default", "VOD.L");
    await flush();

    expect(api.putSavedWatchlists).not.toHaveBeenCalled();
  });

  it("never syncs a demo session", async () => {
    (isDemoSession as Mock).mockReturnValue(true);

    await ensureWatchlistsLoaded();
    toggleInWatchlist("default", "VOD.L");
    await flush();

    expect(api.getSavedWatchlists).not.toHaveBeenCalled();
    expect(api.putSavedWatchlists).not.toHaveBeenCalled();
  });

  it("loads again for the new identity after a sign-in, but not after a logout", async () => {
    (api.getSavedWatchlists as Mock).mockResolvedValue(saved(SERVER));
    await ensureWatchlistsLoaded();
    expect(api.getSavedWatchlists).toHaveBeenCalledTimes(1);

    emitAuthChange({ previousToken: "a", nextToken: null });
    expect(api.getSavedWatchlists).toHaveBeenCalledTimes(1);

    const bobs = list("Bob's", ["GSK.L"]);
    (api.getSavedWatchlists as Mock).mockResolvedValue(saved(bobs, 1, "bob"));
    emitAuthChange({ previousToken: null, nextToken: "b" });
    await vi.waitFor(() => expect(readWatchlists()).toEqual(bobs));
  });
});
