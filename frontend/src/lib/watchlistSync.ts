import * as api from "../api";
import { isLogout, onAuthChange } from "../authEvents";
import { isDemoSession } from "../demoAuth";
import {
  adoptWatchlists,
  defaultWatchlists,
  hasStoredWatchlists,
  onWatchlistsEdited,
  readWatchlists,
  type WatchlistsState,
} from "./watchlistStore";

// Keeps the watchlists in watchlistStore.ts (cached in localStorage) in step
// with the signed-in user's copy on the server (#10713), so they survive
// clearing site data and follow the user to other browsers and devices.
//
// - Load: ensureWatchlistsLoaded() fetches the saved copy once per identity.
//   The server's copy wins, except over edits this browser has not saved yet
//   for the same user, which are saved instead (a conflict then decides).
//   The first time a browser syncs and the server has nothing, the lists
//   this browser already holds (edited, or the legacy single list) are
//   uploaded once; the localStorage keys are kept, so a rollback still finds
//   them. A cache belonging to a different user is replaced, never uploaded.
// - Save: each edit is saved after a short debounce, as a PUT naming the
//   revision it was based on. A 409 means another tab or device saved first:
//   the saved copy is adopted (last writer loses).
// - Failures never break the watchlists: they carry on locally, the failure
//   is logged, and the next edit retries.
//
// Demo sessions are read-only and share one identity, so they never sync, and
// a caller with no identity (owner null) keeps its lists local.

export const WATCHLISTS_SYNC_STORAGE_KEY = "watchlistsSync";
export const SAVE_DEBOUNCE_MS = 500;

interface SyncState {
  /** Opaque server id of the user the cached lists belong to; null before the first sync. */
  owner: string | null;
  /** Server revision the cached lists are based on. */
  revision: number;
  /** True while the cache holds edits the server does not have yet. */
  dirty: boolean;
}

const UNSYNCED: SyncState = { owner: null, revision: 0, dirty: false };

let epoch = 0;
let loadedEpoch: number | null = null;
let requested = false;
let serverOwner: string | null = null;
let loading: Promise<void> | null = null;
let saving: Promise<void> | null = null;
let saveTimer: ReturnType<typeof setTimeout> | null = null;

// Shared by every tab, like the lists themselves, so a save in one tab moves
// the revision the others will base theirs on.
function readSync(): SyncState {
  try {
    const raw = localStorage.getItem(WATCHLISTS_SYNC_STORAGE_KEY);
    if (!raw) return UNSYNCED;
    const parsed = JSON.parse(raw) as Partial<SyncState>;
    return {
      owner: typeof parsed.owner === "string" ? parsed.owner : null,
      revision: typeof parsed.revision === "number" ? parsed.revision : 0,
      dirty: parsed.dirty === true,
    };
  } catch (err) {
    console.warn("Ignoring unreadable watchlist sync state:", err);
    return UNSYNCED;
  }
}

function writeSync(next: SyncState): void {
  localStorage.setItem(WATCHLISTS_SYNC_STORAGE_KEY, JSON.stringify(next));
}

function syncEnabled(): boolean {
  return !isDemoSession();
}

function isSaved(value: unknown): value is api.SavedWatchlists {
  const v = value as Partial<api.SavedWatchlists> | null;
  return (
    !!v &&
    (typeof v.owner === "string" || v.owner === null) &&
    typeof v.revision === "number" &&
    (v.state === null || typeof v.state === "object")
  );
}

/** What the cache should hold, and whether it still needs saving, after loading `saved`. */
function reconcile(saved: api.SavedWatchlists & { owner: string }, local: SyncState) {
  const synced = { owner: saved.owner, revision: saved.revision, dirty: false };
  if (local.owner !== null && local.owner !== saved.owner) {
    // Cached for someone else: never upload it into this account.
    return { adopt: saved.state ?? defaultWatchlists(), sync: synced };
  }
  if (local.owner === saved.owner && local.dirty) {
    // Unsaved edits for this user: keep them and save them.
    return { adopt: null, sync: local };
  }
  if (saved.state) return { adopt: saved.state, sync: synced };
  // Nothing on the server: a first sync uploads what this browser holds.
  const upload = local.owner === null ? hasStoredWatchlists() : local.dirty;
  return { adopt: null, sync: { ...synced, dirty: upload } };
}

async function load(): Promise<void> {
  const myEpoch = epoch;
  let saved: api.SavedWatchlists;
  try {
    saved = await api.getSavedWatchlists();
    if (!isSaved(saved)) throw new Error("Unexpected response from GET /watchlists");
  } catch (err) {
    console.warn("Watchlists were not loaded from the server", err);
    return;
  }
  if (myEpoch !== epoch) return; // signed out or switched meanwhile
  loadedEpoch = myEpoch;
  serverOwner = saved.owner;
  if (saved.owner === null) return; // no identity: the lists stay local
  const { adopt, sync } = reconcile({ ...saved, owner: saved.owner }, readSync());
  if (adopt) adoptWatchlists(adopt);
  writeSync(sync);
}

/** Loads the saved watchlists once per identity, then saves anything pending. Never rejects. */
export function ensureWatchlistsLoaded(): Promise<void> {
  requested = true;
  if (!syncEnabled() || loadedEpoch === epoch) return Promise.resolve();
  if (!loading) {
    loading = load()
      // Only once loaded: flush() waits on this very promise otherwise.
      .then(() => (loadedEpoch === epoch ? flush() : undefined))
      .finally(() => {
        loading = null;
      });
  }
  return loading;
}

function isConflict(
  err: unknown,
): err is { body: { current: { revision: number; state: WatchlistsState | null } } } {
  const e = err as { status?: unknown; body?: { current?: { revision?: unknown } } } | null;
  return e?.status === 409 && typeof e.body?.current?.revision === "number";
}

async function saveOnce(myEpoch: number): Promise<void> {
  const snapshot = JSON.stringify(readWatchlists());
  try {
    const { revision } = await api.putSavedWatchlists(
      JSON.parse(snapshot) as WatchlistsState,
      readSync().revision,
    );
    if (myEpoch !== epoch) return;
    // Edited again while saving: stay dirty so the next save picks it up.
    const dirty = JSON.stringify(readWatchlists()) !== snapshot;
    writeSync({ ...readSync(), revision, dirty });
  } catch (err) {
    if (!isConflict(err)) throw err;
    if (myEpoch !== epoch) return;
    const { current } = err.body;
    if (current.state) {
      adoptWatchlists(current.state);
      writeSync({ ...readSync(), revision: current.revision, dirty: false });
    } else {
      // Deleted on the server meanwhile: upload this copy again.
      writeSync({ ...readSync(), revision: current.revision, dirty: true });
    }
  }
}

/** Saves now if anything is unsaved; waits for a save already running. Never rejects. */
export async function flush(): Promise<void> {
  if (saveTimer) {
    clearTimeout(saveTimer);
    saveTimer = null;
  }
  if (!syncEnabled() || !readSync().dirty) return;
  if (loadedEpoch !== epoch) {
    await ensureWatchlistsLoaded();
    return;
  }
  if (serverOwner === null) return;
  if (saving) {
    await saving;
    return flush();
  }
  let failed = false;
  saving = saveOnce(epoch)
    .catch((err) => {
      failed = true;
      console.warn("Watchlists were not saved to the server", err);
    })
    .finally(() => {
      saving = null;
    });
  await saving;
  if (!failed && readSync().dirty) scheduleSave();
}

function scheduleSave() {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    saveTimer = null;
    void flush();
  }, SAVE_DEBOUNCE_MS);
}

function handleEdit() {
  if (!syncEnabled()) return;
  writeSync({ ...readSync(), dirty: true });
  if (requested) scheduleSave();
}

onWatchlistsEdited(handleEdit);

onAuthChange((change) => {
  epoch += 1;
  loadedEpoch = null;
  serverOwner = null;
  // After a logout there is no one to load for; the next sign-in loads.
  if (requested && !isLogout(change)) void ensureWatchlistsLoaded();
});

/** For tests: forget everything loaded and stop pending saves. */
export function resetWatchlistSyncForTests() {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = null;
  epoch = 0;
  loadedEpoch = null;
  requested = false;
  serverOwner = null;
  loading = null;
  saving = null;
}
