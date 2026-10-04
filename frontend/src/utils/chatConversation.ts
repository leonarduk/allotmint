import { useSyncExternalStore } from "react";
import type { ChatMessage, SavedChatTree } from "../api";
import { isLogout, onAuthChange } from "../authEvents";

// The chat conversation outlives ChatPanel: AppHeader (and so ChatPanel) is
// mounted per page, so component state was lost on every navigation. Keeping
// it here carries the conversation across pages; sessionStorage also carries
// it across a reload of the same tab. It is cleared by resetChat(), which
// also runs on logout via the authEvents subscriber below. The server copy
// (#8870) is kept in step by utils/chatSync.ts, which learns of each change
// through onChatChange().
//
// The conversation is a tree, so editing a message or regenerating a reply
// keeps the earlier version as a sibling branch (#8842). `active` records the
// selected child of each node (ROOT for the first turn); following it from
// the root gives the active path, which is all the panel shows and all that
// is sent to the backend as history.
const STORAGE_KEY = "allotmint.chat.tree.v1";
// Flat ChatMessage[] stored before #8842: migrated as a single branch.
const LEGACY_STORAGE_KEY = "allotmint.chat.messages";
// Where this tab's copy stands against the server's (#8870); see ChatSyncState.
const SYNC_STORAGE_KEY = "allotmint.chat.sync.v1";
const ROOT = "root";

export interface ChatNode extends ChatMessage {
  id: string;
  parentId: string | null;
}

/** A node on the active path, with its position among its versions. */
export interface ChatPathEntry extends ChatNode {
  /** 1-based index of this version among its siblings. */
  version: number;
  versionCount: number;
}

interface ChatTree {
  /** In creation order, so a parent always precedes its children. */
  nodes: ChatNode[];
  active: Record<string, string>;
  nextId: number;
}

/** Opaque copy of the conversation, for rolling back a failed request. */
export type ChatSnapshot = Readonly<ChatTree>;

/** Where this tab's conversation stands against the saved one (#8870). */
export interface ChatSyncState {
  /** Whose saved conversation this is (GET /chat/conversation `owner`); null until first loaded. */
  owner: string | null;
  /** The saved revision this copy was loaded from or last saved as. */
  revision: number;
  /** Changed since then, so not yet saved. */
  dirty: boolean;
  /** "New chat" was pressed but the saved conversation is not yet archived. */
  archivePending: boolean;
}

function isMessage(m: unknown): m is ChatMessage {
  const msg = m as Partial<ChatMessage> | null;
  return (msg?.role === "user" || msg?.role === "assistant") && typeof msg.content === "string";
}

function emptyTree(): ChatTree {
  return { nodes: [], active: {}, nextId: 1 };
}

function linearTree(messages: ChatMessage[]): ChatTree {
  const tree = emptyTree();
  let parentId: string | null = null;
  for (const { role, content } of messages) {
    const id = String(tree.nextId++);
    tree.nodes.push({ id, parentId, role, content });
    tree.active[parentId ?? ROOT] = id;
    parentId = id;
  }
  return tree;
}

function parseNodes(raw: unknown): ChatNode[] {
  const nodes: ChatNode[] = [];
  const ids = new Set<string>();
  for (const n of Array.isArray(raw) ? raw : []) {
    const node = n as Partial<ChatNode>;
    const { id, parentId } = node;
    const parentOk = parentId === null || (typeof parentId === "string" && ids.has(parentId));
    if (!isMessage(node) || typeof id !== "string" || ids.has(id) || !parentOk) continue;
    ids.add(id);
    nodes.push({ id, parentId: parentId ?? null, role: node.role, content: node.content });
  }
  return nodes;
}

// Rebuild a stored tree defensively: drop nodes that are malformed, reuse an
// id, or whose parent is missing (parents precede children), and active
// entries that do not point at a child of their key.
function parseTree(raw: unknown): ChatTree {
  const data = raw as Partial<ChatTree> | null;
  const nodes = parseNodes(data?.nodes);
  const active: Record<string, string> = {};
  const storedActive = data?.active && typeof data.active === "object" ? data.active : {};
  for (const [key, childId] of Object.entries(storedActive)) {
    const child = nodes.find((node) => node.id === childId);
    if (child && (child.parentId ?? ROOT) === key) active[key] = child.id;
  }
  const maxId = Math.max(0, ...nodes.map((node) => Number(node.id) || 0));
  const storedNext = typeof data?.nextId === "number" ? data.nextId : 1;
  return { nodes, active, nextId: Math.max(maxId + 1, storedNext) };
}

function readJson(key: string): unknown {
  const stored = sessionStorage.getItem(key);
  return stored === null ? null : JSON.parse(stored);
}

function loadSyncState(stored: ChatTree): ChatSyncState {
  try {
    const raw = readJson(SYNC_STORAGE_KEY) as Partial<ChatSyncState> | null;
    if (raw && typeof raw === "object") {
      return {
        owner: typeof raw.owner === "string" ? raw.owner : null,
        revision: typeof raw.revision === "number" ? raw.revision : 0,
        dirty: raw.dirty === true,
        archivePending: raw.archivePending === true,
      };
    }
  } catch {
    // Unreadable: treated as never synced, below.
  }
  // Never synced: anything held locally has not been saved.
  return { owner: null, revision: 0, dirty: stored.nodes.length > 0, archivePending: false };
}

function load(): ChatTree {
  try {
    const stored = readJson(STORAGE_KEY);
    if (stored !== null) return parseTree(stored);
    const legacy = readJson(LEGACY_STORAGE_KEY);
    return linearTree(Array.isArray(legacy) ? legacy.filter(isMessage) : []);
  } catch {
    return emptyTree();
  }
}

function siblingsOf(tree: ChatTree, node: ChatNode): ChatNode[] {
  return tree.nodes.filter((n) => n.parentId === node.parentId);
}

function activePath(tree: ChatTree): ChatPathEntry[] {
  const path: ChatPathEntry[] = [];
  let id: string | undefined = tree.active[ROOT];
  // Bounded by the node count, so corrupt data cannot loop forever.
  while (id !== undefined && path.length < tree.nodes.length) {
    const node = tree.nodes.find((n) => n.id === id);
    if (!node) break;
    const siblings = siblingsOf(tree, node);
    path.push({ ...node, version: siblings.indexOf(node) + 1, versionCount: siblings.length });
    id = tree.active[node.id];
  }
  return path;
}

let tree: ChatTree = load();
let syncState: ChatSyncState = loadSyncState(tree);
// Derived once per change so useSyncExternalStore sees stable snapshots.
let path: ChatPathEntry[] = activePath(tree);
let messages: ChatMessage[] = path.map(({ role, content }) => ({ role, content }));
const listeners = new Set<() => void>();
let changeListener: (() => void) | null = null;
// Bumped whenever the signed-in identity may have changed, so chatSync knows
// to reload before trusting what it last loaded.
let identityEpoch = 0;

// `byUser` is false for changes that come from the server or a logout, which
// must not be saved back.
function set(next: ChatTree, byUser = true) {
  tree = next;
  path = activePath(next);
  messages = path.map(({ role, content }) => ({ role, content }));
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    sessionStorage.removeItem(LEGACY_STORAGE_KEY);
  } catch {
    // Storage unavailable or full: the in-memory conversation still works.
  }
  listeners.forEach((l) => l());
  if (byUser) changeListener?.();
}

function addNode(parentId: string | null, message: ChatMessage): string {
  const id = String(tree.nextId);
  set({
    nodes: [...tree.nodes, { id, parentId, role: message.role, content: message.content }],
    active: { ...tree.active, [parentId ?? ROOT]: id },
    nextId: tree.nextId + 1,
  });
  return id;
}

/** The active path's messages, as sent to the backend as history. */
export function getChatMessages(): ChatMessage[] {
  return messages;
}

/** The active path's nodes, with each one's version position. */
export function getChatPath(): ChatPathEntry[] {
  return path;
}

/** Replaces the whole conversation with a single branch of `next`. */
export function setChatMessages(next: ChatMessage[]) {
  set(linearTree(next));
}

/** Adds `message` after the last turn of the active path; returns its id. */
export function appendChatMessage(message: ChatMessage): string {
  return addNode(path.at(-1)?.id ?? null, message);
}

/**
 * Adds `message` as a new version of node `id` and selects it, so the active
 * path ends at the new node. The old version keeps its later turns.
 */
export function addChatVersion(id: string, message: ChatMessage): string {
  const node = tree.nodes.find((n) => n.id === id);
  if (!node) throw new Error(`Unknown chat message ${id}`);
  return addNode(node.parentId, message);
}

/**
 * Ends the active path at node `id` without discarding anything below it, so
 * the next appended turn becomes a new version of the reply that followed.
 */
export function endChatPathAt(id: string) {
  const active = { ...tree.active };
  delete active[id];
  set({ ...tree, active });
}

/** Selects the version `offset` steps from node `id` among its siblings. */
export function selectChatVersion(id: string, offset: number) {
  const node = tree.nodes.find((n) => n.id === id);
  if (!node) return;
  const siblings = siblingsOf(tree, node);
  const target = siblings[siblings.indexOf(node) + offset];
  if (!target) return;
  set({ ...tree, active: { ...tree.active, [node.parentId ?? ROOT]: target.id } });
}

export function snapshotChat(): ChatSnapshot {
  return tree;
}

export function restoreChat(snapshot: ChatSnapshot) {
  set(snapshot);
}

/** Clears the conversation in this tab only; the saved copy is left alone. */
export function startNewChat() {
  set(emptyTree());
}

/**
 * Logout: forgets the conversation and everything known about the saved
 * copy, without touching the server, so the next user to sign in on this tab
 * starts from their own saved conversation.
 */
export function resetChat() {
  identityEpoch += 1;
  setChatSyncState({ owner: null, revision: 0, dirty: false, archivePending: false });
  set(emptyTree(), false);
}

/** The signed-in identity may have changed (a new token): reload before saving. */
export function markChatIdentityChanged() {
  identityEpoch += 1;
}

export function getChatIdentityEpoch(): number {
  return identityEpoch;
}

/** Replaces the conversation with a saved one, without it counting as a change to save. */
export function adoptSavedChat(saved: SavedChatTree) {
  set(parseTree(saved), false);
}

export function getChatSyncState(): ChatSyncState {
  return syncState;
}

export function setChatSyncState(next: ChatSyncState) {
  syncState = next;
  try {
    sessionStorage.setItem(SYNC_STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Storage unavailable or full: the in-memory state still works.
  }
}

/** Registers the one listener told of every change made by the user (utils/chatSync.ts). */
export function onChatChange(listener: (() => void) | null) {
  changeListener = listener;
}

// Clear on logout only, not on every token change: a reload re-applies the
// stored token from null, and the Cognito refresh swaps in a new token for the
// same user every hour. Registered at module load; main.tsx imports this
// module statically (via AppHeader -> ChatPanel), so the subscriber is in
// place before any logout can happen.
//
// Logout uses resetChat(), not startNewChat(): the latter counts as a change
// by the user and would save an empty conversation over the saved one. The
// saved copy stays with the user (#8870). Any other new token may be a
// different user, so the chat sync reloads before it saves again and never
// uploads one user's cached conversation into another's account.
onAuthChange((change) => {
  if (isLogout(change)) resetChat();
  else if (change.nextToken !== null) markChatIdentityChanged();
});

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useChatMessages(): ChatMessage[] {
  return useSyncExternalStore(subscribe, getChatMessages, getChatMessages);
}

export function useChatPath(): ChatPathEntry[] {
  return useSyncExternalStore(subscribe, getChatPath, getChatPath);
}
