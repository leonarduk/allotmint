import { useSyncExternalStore } from "react";
import type { ChatMessage } from "../api";

// The chat conversation outlives ChatPanel: AppHeader (and so ChatPanel) is
// mounted per page, so component state was lost on every navigation. Keeping
// it here carries the conversation across pages; sessionStorage also carries
// it across a reload of the same tab. It is cleared only by startNewChat().
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

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useChatMessages(): ChatMessage[] {
  return useSyncExternalStore(subscribe, getChatMessages, getChatMessages);
}
