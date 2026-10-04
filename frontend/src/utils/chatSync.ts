import { useSyncExternalStore } from "react";
import * as api from "../api";
import type { SavedChatTree } from "../api";
import { isDemoSession } from "../demoAuth";
import {
  adoptSavedChat,
  getChatIdentityEpoch,
  getChatSyncState,
  onChatChange,
  setChatSyncState,
  snapshotChat,
  startNewChat,
} from "./chatConversation";

// Keeps the conversation in chatConversation.ts in step with the copy saved
// on the server (#8870), so it survives closing the tab and follows the user
// to other devices.
//
// - Load: ensureChatLoaded() fetches the saved copy and adopts it, unless this
//   tab holds unsaved changes, which are saved instead: for the same user a
//   conflict then decides; before this tab's first sync, a different saved
//   conversation is archived first, so neither copy is lost. A copy cached
//   for a different user is discarded.
// - Save: each change is saved after a short debounce, as a PUT naming the
//   revision it was based on. A 409 means another tab or device saved first:
//   the saved copy is adopted (last writer loses).
// - New chat archives the saved copy; deleteSavedChatHistory() deletes it all.
// - Failures never break chat: the conversation carries on locally, the
//   failure is logged and shown as a "not saved" hint, and the next change
//   retries.
//
// Demo sessions are read-only and share one identity, so they never sync.

export const SAVE_DEBOUNCE_MS = 800;

let loadedEpoch: number | null = null;
let loading: Promise<void> | null = null;
let saving: Promise<void> | null = null;
let saveTimer: ReturnType<typeof setTimeout> | null = null;
let replyPending = false;
let failed = false;
const statusListeners = new Set<() => void>();

function setFailed(next: boolean, error?: unknown) {
  if (error !== undefined) console.warn("Chat history was not saved", error);
  if (failed === next) return;
  failed = next;
  statusListeners.forEach((l) => l());
}

function updateSync(patch: Partial<ReturnType<typeof getChatSyncState>>) {
  setChatSyncState({ ...getChatSyncState(), ...patch });
}

function syncEnabled(): boolean {
  return !isDemoSession();
}

function isEmpty(conversation: SavedChatTree | undefined): boolean {
  return !conversation?.nodes?.length;
}

async function load(): Promise<void> {
  const epoch = getChatIdentityEpoch();
  let saved: api.SavedChatConversation;
  try {
    saved = await api.getChatConversation();
    if (typeof saved?.owner !== "string" || typeof saved.revision !== "number") {
      throw new Error("Unexpected response from GET /chat/conversation");
    }
  } catch (e) {
    setFailed(true, e);
    return;
  }
  if (epoch !== getChatIdentityEpoch()) return; // signed out or switched meanwhile
  // A question went out meanwhile: adopting now could drop it, so load again
  // once its reply is in (setChatReplyPending(false) schedules that).
  if (replyPending) return;
  const local = getChatSyncState();
  const sameUser = local.owner === saved.owner;
  if (local.owner !== null && !sameUser) {
    // Cached for someone else: never upload it into this account.
    adoptSavedChat(saved.conversation);
    setChatSyncState({ owner: saved.owner, revision: saved.revision, dirty: false, archivePending: false });
  } else if (local.archivePending || local.dirty) {
    // Unsaved local work: keep it and save it, below. Before this tab's first
    // sync (no owner yet) a different saved conversation is archived first.
    const revision = sameUser ? local.revision : saved.revision;
    const archiveSaved = !sameUser && !isEmpty(saved.conversation);
    setChatSyncState({ ...local, owner: saved.owner, revision, archivePending: local.archivePending || archiveSaved });
  } else {
    adoptSavedChat(saved.conversation);
    setChatSyncState({ owner: saved.owner, revision: saved.revision, dirty: false, archivePending: false });
  }
  loadedEpoch = epoch;
  setFailed(false);
}

/** Loads the saved conversation once per signed-in identity. Never rejects. */
export function ensureChatLoaded(): Promise<void> {
  if (!syncEnabled() || loadedEpoch === getChatIdentityEpoch()) return Promise.resolve();
  if (!loading) {
    loading = load()
      // Only once loaded: flush() waits on this very promise otherwise.
      .then(() => (loadedEpoch === getChatIdentityEpoch() ? flush() : undefined))
      .finally(() => {
        loading = null;
      });
  }
  return loading;
}

function isConflict(e: unknown): e is { body: { current: { revision: number; conversation: SavedChatTree } } } {
  const err = e as { status?: unknown; body?: { current?: { revision?: unknown } } } | null;
  return err?.status === 409 && typeof err.body?.current?.revision === "number";
}

async function saveOnce(epoch: number): Promise<void> {
  const state = getChatSyncState();
  if (state.archivePending) {
    const { revision } = await api.archiveChatConversation();
    if (epoch !== getChatIdentityEpoch()) return;
    updateSync({ revision, archivePending: false });
  }
  if (!getChatSyncState().dirty) return;
  const snapshot = snapshotChat();
  try {
    const { revision } = await api.putChatConversation(snapshot, getChatSyncState().revision);
    if (epoch !== getChatIdentityEpoch()) return;
    // Changed again while saving: stay dirty so the next save picks it up.
    updateSync({ revision, dirty: snapshotChat() !== snapshot });
  } catch (e) {
    if (!isConflict(e)) throw e;
    if (epoch !== getChatIdentityEpoch()) return;
    const { current } = e.body;
    adoptSavedChat(current.conversation);
    updateSync({ revision: current.revision, dirty: false });
  }
}

/** Saves now if anything is unsaved; waits for a save already running. Never rejects. */
export async function flush(): Promise<void> {
  if (saveTimer) {
    clearTimeout(saveTimer);
    saveTimer = null;
  }
  if (!syncEnabled() || replyPending) return;
  const { dirty, archivePending } = getChatSyncState();
  if (!dirty && !archivePending) return;
  if (loadedEpoch !== getChatIdentityEpoch()) {
    await ensureChatLoaded();
    return;
  }
  if (saving) {
    await saving;
    return flush();
  }
  const epoch = getChatIdentityEpoch();
  saving = saveOnce(epoch)
    .then(() => setFailed(false))
    .catch((e) => setFailed(true, e))
    .finally(() => {
      saving = null;
    });
  await saving;
  const after = getChatSyncState();
  if (!failed && (after.dirty || after.archivePending)) scheduleSave();
}

function scheduleSave() {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    saveTimer = null;
    void flush();
  }, SAVE_DEBOUNCE_MS);
}

function handleChange() {
  if (!syncEnabled()) return;
  updateSync({ dirty: true });
  scheduleSave();
}

/**
 * Holds saves while a reply is pending: until it arrives the conversation
 * ends in an unanswered question, and a failed request rolls it back anyway.
 */
export function setChatReplyPending(pending: boolean) {
  replyPending = pending;
  if (!pending && getChatSyncState().dirty) scheduleSave();
}

/** "New chat": clears the conversation here and archives the saved one. */
export function startNewSavedChat() {
  startNewChat();
  if (!syncEnabled()) return;
  updateSync({ dirty: false, archivePending: true });
  void flush();
}

/**
 * Deletes the saved chat history (the current conversation and every archived
 * one) and clears it here. Rejects, leaving the conversation as it was, when
 * the server could not delete it.
 */
export async function deleteSavedChatHistory(): Promise<void> {
  if (saveTimer) {
    clearTimeout(saveTimer);
    saveTimer = null;
  }
  // A save finishing after the delete would recreate what was just deleted.
  if (saving) await saving;
  await api.deleteChatHistory();
  adoptSavedChat({ nodes: [], active: {}, nextId: 1 });
  updateSync({ revision: 0, dirty: false, archivePending: false });
  setFailed(false);
}

function subscribeStatus(listener: () => void) {
  statusListeners.add(listener);
  return () => {
    statusListeners.delete(listener);
  };
}

const getFailed = () => failed;

/** True while the last load or save failed, so the conversation may not be saved. */
export function useChatSaveFailed(): boolean {
  return useSyncExternalStore(subscribeStatus, getFailed, getFailed);
}

/** For tests: forget everything loaded and stop pending saves. */
export function resetChatSyncForTests() {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = null;
  loadedEpoch = null;
  loading = null;
  saving = null;
  replyPending = false;
  failed = false;
}

onChatChange(handleChange);
