import { useSyncExternalStore } from "react";
import type { ChatMessage } from "../api";
import { isLogout, onAuthChange } from "../authEvents";

// The chat conversation outlives ChatPanel: AppHeader (and so ChatPanel) is
// mounted per page, so component state was lost on every navigation. Keeping
// it here carries the conversation across pages; sessionStorage also carries
// it across a reload of the same tab. It is cleared by startNewChat(), which
// also runs on logout via the authEvents subscriber below.
const STORAGE_KEY = "allotmint.chat.messages";

function isMessage(m: unknown): m is ChatMessage {
  const msg = m as Partial<ChatMessage> | null;
  return (
    (msg?.role === "user" || msg?.role === "assistant") && typeof msg.content === "string"
  );
}

function load(): ChatMessage[] {
  try {
    const parsed: unknown = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter(isMessage) : [];
  } catch {
    return [];
  }
}

let messages: ChatMessage[] = load();
const listeners = new Set<() => void>();

function set(next: ChatMessage[]) {
  messages = next;
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Storage unavailable or full: the in-memory conversation still works.
  }
  listeners.forEach((l) => l());
}

export function getChatMessages(): ChatMessage[] {
  return messages;
}

export function setChatMessages(next: ChatMessage[]) {
  set(next);
}

export function appendChatMessage(message: ChatMessage) {
  set([...messages, message]);
}

export function startNewChat() {
  set([]);
}

// Clear on logout only, not on every token change: a reload re-applies the
// stored token from null, and the Cognito refresh swaps in a new token for the
// same user every hour. Registered at module load; main.tsx imports this
// module statically (via AppHeader -> ChatPanel), so the subscriber is in
// place before any logout can happen.
onAuthChange((change) => {
  if (isLogout(change)) startNewChat();
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
