import { useSyncExternalStore } from "react";
import type { ChatMessage } from "../api";

// The chat conversation outlives ChatPanel: AppHeader (and so ChatPanel) is
// mounted per page, so component state was lost on every navigation. Keeping
// it here carries the conversation across pages; sessionStorage also carries
// it across a reload of the same tab. It is cleared by startNewChat(), which
// api.setAuthToken also calls on logout.
//
// The conversation is a tree, so editing a message or regenerating a reply
// keeps the earlier version as a sibling branch (#8842). `active` records the
// selected child of each node (ROOT for the first turn); following it from
// the root gives the active path, which is all the panel shows and all that
// is sent to the backend as history.
const STORAGE_KEY = "allotmint.chat.tree.v1";
// Flat ChatMessage[] stored before #8842: migrated as a single branch.
const LEGACY_STORAGE_KEY = "allotmint.chat.messages";
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
// Derived once per change so useSyncExternalStore sees stable snapshots.
let path: ChatPathEntry[] = activePath(tree);
let messages: ChatMessage[] = path.map(({ role, content }) => ({ role, content }));
const listeners = new Set<() => void>();

function set(next: ChatTree) {
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

export function startNewChat() {
  set(emptyTree());
}

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
