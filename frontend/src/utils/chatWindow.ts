import { useEffect, useState, useSyncExternalStore } from "react";
import type { ChatContext, ChatPage } from "../api";
import { isLogout, onAuthChange } from "../authEvents";
import { buildChatContext } from "./chatPages";
import {
  adoptChatFromWindow,
  getChatSyncState,
  onChatStateChange,
  snapshotChat,
  type ChatSyncState,
} from "./chatConversation";

// Detaching the chat into its own window and reattaching it (#9025).
//
// The main window opens CHAT_WINDOW_PATH as a popup. The two talk over a
// BroadcastChannel, every message naming the main window it belongs to, so
// other tabs of the app (each with their own popup) ignore it:
//
// - Conversation: each window posts its conversation and sync state on every
//   change, and the other adopts it without saving it (the window that made
//   the change saves it), so reattaching shows the same conversation.
// - Page context: the main window posts the page the user is on, which the
//   popup sends with each turn.
// - Navigation: when the assistant opens a page, the popup asks the main
//   window to go there; the popup stays open.
// - Reattach: the popup's Reattach button tells the main window, which opens
//   the chat drawer again, and then closes itself. Closing the popup any other
//   way also reattaches, without opening the drawer.
//
// The main window's side is module state, not component state: AppHeader is
// mounted per page, and the popup must stay linked across navigation.

export const CHAT_WINDOW_PATH = "/chat-window";
const CHANNEL_NAME = "allotmint.chat.window.v1";
// Names this tab's main window across reloads, in sessionStorage.
const MAIN_ID_KEY = "allotmint.chat.mainWindowId";
// "detached" or "attached": how the user last chose to use the chat.
const PREFERENCE_KEY = "allotmint.chat.mode";
const POPUP_FEATURES = "popup,width=480,height=720";
// The popup says it is still there this often. A popup the main window holds
// no reference to (the main window reloaded) is taken as closed once silent
// for STALE_MS: well over a minute, since a minimised window's timers may be
// throttled to once a minute.
export const HEARTBEAT_MS = 5_000;
export const STALE_MS = 75_000;
// After the popup says it is going away, how long a reload has to say hello again.
export const CLOSE_GRACE_MS = 2_000;
// The narrowest viewport offered Detach; below it the chat is a full-width drawer.
const DETACH_MIN_WIDTH = "(min-width: 768px)";

type WindowMessage =
  | { type: "hello"; main: string }
  | { type: "alive"; main: string }
  | { type: "closing"; main: string }
  | { type: "ping"; main: string }
  | { type: "state"; main: string; tree: unknown; sync: ChatSyncState }
  | { type: "context"; main: string; context: ChatContext }
  | { type: "navigate"; main: string; path: string }
  | { type: "reattach"; main: string }
  | { type: "logout"; main: string };

// A message as a window composes it; post() adds the main window's id.
type WithoutMain<M> = M extends unknown ? Omit<M, "main"> : never;
type Outgoing = WithoutMain<WindowMessage>;

function isWindowMessage(data: unknown): data is WindowMessage {
  const msg = data as { type?: unknown; main?: unknown } | null;
  return typeof msg?.type === "string" && typeof msg.main === "string";
}

function openChannel(): BroadcastChannel | null {
  return typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel(CHANNEL_NAME);
}

function readStorage(storage: Storage, key: string): string | null {
  try {
    return storage.getItem(key);
  } catch {
    return null; // Storage blocked: treated as never set.
  }
}

function writeStorage(storage: Storage, key: string, value: string) {
  try {
    storage.setItem(key, value);
  } catch {
    // Storage blocked or full: the setting just isn't remembered.
  }
}

/** True when the browser can detach the chat and the viewport is wide enough to want it. */
export function canDetachChat(): boolean {
  return typeof BroadcastChannel !== "undefined" && window.matchMedia?.(DETACH_MIN_WIDTH).matches === true;
}

/** True when the user last chose the detached chat. */
export function prefersDetachedChat(): boolean {
  return readStorage(localStorage, PREFERENCE_KEY) === "detached";
}

/**
 * Mirrors this window's conversation to the other one and adopts theirs.
 * Returns the unsubscribe.
 */
function mirrorConversation(channel: BroadcastChannel, main: string): () => void {
  let adopting = false;
  const post = () => {
    if (adopting) return;
    channel.postMessage({ type: "state", main, tree: snapshotChat(), sync: getChatSyncState() });
  };
  const adopt = (msg: WindowMessage) => {
    if (msg.type !== "state") return;
    adopting = true;
    try {
      adoptChatFromWindow(msg.tree, msg.sync);
    } finally {
      adopting = false;
    }
  };
  const unsubscribe = onChatStateChange(post);
  const listener = (event: MessageEvent) => {
    if (isWindowMessage(event.data) && event.data.main === main) adopt(event.data);
  };
  channel.addEventListener("message", listener);
  return () => {
    unsubscribe();
    channel.removeEventListener("message", listener);
  };
}

/* ------------------------------------------------------------------ */
/* Main window                                                         */
/* ------------------------------------------------------------------ */

interface HostHandlers {
  pages: ChatPage[];
  context: ChatContext;
  onNavigate: (path: string) => void;
  onReattach: () => void;
}

interface MainState {
  id: string;
  channel: BroadcastChannel;
  popup: Window | null;
  lastSeen: number;
  timer: ReturnType<typeof setInterval> | null;
  stopMirror: (() => void) | null;
}

let main: MainState | null = null;
let detached = false;
let host: HostHandlers | null = null;
const detachedListeners = new Set<() => void>();

function mainId(): string {
  const stored = readStorage(sessionStorage, MAIN_ID_KEY);
  if (stored) return stored;
  // randomUUID is missing outside secure contexts (e.g. a dev server on a LAN address).
  const id = crypto.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  writeStorage(sessionStorage, MAIN_ID_KEY, id);
  return id;
}

function setDetached(next: boolean) {
  if (detached === next) return;
  detached = next;
  detachedListeners.forEach((l) => l());
}

function post(state: MainState, message: Outgoing) {
  state.channel.postMessage({ ...message, main: state.id });
}

function startWatching(state: MainState) {
  state.lastSeen = Date.now();
  state.stopMirror ??= mirrorConversation(state.channel, state.id);
  state.timer ??= setInterval(() => {
    const gone = state.popup ? state.popup.closed : Date.now() - state.lastSeen > STALE_MS;
    if (gone) reattachMain(false);
  }, 1_000);
  setDetached(true);
}

function reattachMain(openDrawer: boolean) {
  if (!main) return;
  if (main.timer) clearInterval(main.timer);
  main.stopMirror?.();
  main.timer = null;
  main.stopMirror = null;
  main.popup = null;
  setDetached(false);
  if (openDrawer) host?.onReattach();
}

function handleMainMessage(state: MainState, msg: WindowMessage) {
  switch (msg.type) {
    case "hello":
      startWatching(state);
      post(state, { type: "state", tree: snapshotChat(), sync: getChatSyncState() });
      if (host) post(state, { type: "context", context: host.context });
      break;
    case "alive":
      if (detached) state.lastSeen = Date.now();
      break;
    case "closing":
      // Reattach unless a reload of the popup says hello again shortly.
      state.lastSeen = Date.now() - STALE_MS + CLOSE_GRACE_MS;
      state.popup = null;
      break;
    case "navigate":
      // Only a page offered to the chat here, as ChatPanel checks too.
      if (!host?.pages.some((page) => page.path === msg.path)) break;
      host.onNavigate(msg.path);
      // Now, not when the new page's header mounts: a slow page would leave
      // the next turn sent with the page the user just left.
      post(state, { type: "context", context: buildChatContext(msg.path) });
      break;
    case "reattach":
      writeStorage(localStorage, PREFERENCE_KEY, "attached");
      reattachMain(true);
      break;
    default:
      break;
  }
}

/** Sets up the main window's side once; null when the browser has no BroadcastChannel. */
function ensureMain(): MainState | null {
  if (main) return main;
  const channel = openChannel();
  if (!channel) return null;
  const state: MainState = { id: mainId(), channel, popup: null, lastSeen: 0, timer: null, stopMirror: null };
  channel.addEventListener("message", (event: MessageEvent) => {
    if (isWindowMessage(event.data) && event.data.main === state.id) handleMainMessage(state, event.data);
  });
  main = state;
  // After a reload, a popup still open from before answers with hello.
  post(state, { type: "ping" });
  return state;
}

/**
 * Opens the chat in its own window, or focuses it when already open. Returns
 * false when the browser blocked the window, leaving the chat attached.
 */
export function openChatWindow(): boolean {
  const state = ensureMain();
  if (!state) return false;
  if (state.popup && !state.popup.closed) {
    state.popup.focus();
    return true;
  }
  const url = `${CHAT_WINDOW_PATH}?main=${encodeURIComponent(state.id)}`;
  const popup = window.open(url, `allotmint-chat-${state.id}`, POPUP_FEATURES);
  if (!popup) return false;
  state.popup = popup;
  writeStorage(localStorage, PREFERENCE_KEY, "detached");
  startWatching(state);
  popup.focus();
  return true;
}

function subscribeDetached(listener: () => void) {
  detachedListeners.add(listener);
  return () => {
    detachedListeners.delete(listener);
  };
}

const getDetached = () => detached;

/**
 * The main window's side: registers how to navigate and reopen the drawer,
 * keeps the popup told of the page the user is on, and returns whether the
 * chat is detached.
 */
export function useChatWindowHost(handlers: HostHandlers): boolean {
  const { context } = handlers;
  useEffect(() => {
    host = handlers;
  });
  useEffect(() => {
    ensureMain();
    return () => {
      host = null;
    };
  }, []);
  // `context` must be memoised by the caller, or this posts on every render.
  useEffect(() => {
    if (main && detached) post(main, { type: "context", context });
  }, [context]);
  return useSyncExternalStore(subscribeDetached, getDetached, getDetached);
}

// Signing out closes the chat window: it holds the signed-out user's conversation.
onAuthChange((change) => {
  if (!isLogout(change) || !main) return;
  post(main, { type: "logout" });
  main.popup?.close();
  reattachMain(false);
});

/** For tests: forget the main window's side. */
export function resetChatWindowForTests() {
  reattachMain(false);
  main?.channel.close();
  main = null;
  host = null;
  detached = false;
}

/* ------------------------------------------------------------------ */
/* Detached window                                                     */
/* ------------------------------------------------------------------ */

export interface DetachedChatWindow {
  /** The main window's page, sent with each turn. */
  context: ChatContext | undefined;
  /** False when this window was not opened from the app, so cannot navigate or reattach. */
  linked: boolean;
  navigate: (path: string) => void;
  reattach: () => void;
}

function linkedMainId(): string | null {
  return new URLSearchParams(window.location.search).get("main");
}

/** The detached window's side; `channel` is null when there is nothing to link to. */
function useDetachedChannel(id: string | null, setContext: (c: ChatContext) => void) {
  const [channel, setChannel] = useState<BroadcastChannel | null>(null);
  useEffect(() => {
    const ch = id ? openChannel() : null;
    if (!ch || !id) return;
    const hello = () => ch.postMessage({ type: "hello", main: id });
    const stopMirror = mirrorConversation(ch, id);
    ch.addEventListener("message", (event: MessageEvent) => {
      const msg: unknown = event.data;
      if (!isWindowMessage(msg) || msg.main !== id) return;
      if (msg.type === "context") setContext(msg.context);
      else if (msg.type === "ping") hello(); // the main window reloaded
      else if (msg.type === "logout") window.close();
    });
    const heartbeat = setInterval(() => ch.postMessage({ type: "alive", main: id }), HEARTBEAT_MS);
    const closing = () => ch.postMessage({ type: "closing", main: id });
    window.addEventListener("pagehide", closing);
    hello();
    setChannel(ch);
    return () => {
      clearInterval(heartbeat);
      window.removeEventListener("pagehide", closing);
      stopMirror();
      ch.close();
    };
  }, [id, setContext]);
  return channel;
}

/** Links a window opened by openChatWindow() to the main window that opened it. */
export function useDetachedChatWindow(): DetachedChatWindow {
  const [id] = useState(linkedMainId);
  const [context, setContext] = useState<ChatContext | undefined>(undefined);
  const channel = useDetachedChannel(id, setContext);
  return {
    context,
    linked: channel !== null && id !== null,
    navigate: (path) => {
      if (channel && id) channel.postMessage({ type: "navigate", main: id, path });
    },
    reattach: () => {
      if (channel && id) channel.postMessage({ type: "reattach", main: id });
      window.close();
    },
  };
}
