import { useEffect, useRef, useState } from "react";
import * as api from "../api";
import type { ChatContext, ChatMessage, ChatPage } from "../api";
import {
  addChatVersion,
  appendChatMessage,
  endChatPathAt,
  restoreChat,
  selectChatVersion,
  snapshotChat,
  useChatMessages,
  useChatPath,
} from "../utils/chatConversation";
import {
  deleteSavedChatHistory,
  ensureChatLoaded,
  setChatReplyPending,
  startNewSavedChat,
  useChatSaveFailed,
} from "../utils/chatSync";
import { isDemoSession } from "../demoAuth";
import { ChatMessageItem } from "./ChatMessageItem";

interface Props {
  open: boolean;
  onClose: () => void;
  /** Pages the assistant may open for the user. */
  pages?: ChatPage[];
  /** The page the user is on, sent with each turn. */
  context?: ChatContext;
  /** Called with a page's path when the assistant opens it. */
  onNavigate?: (path: string) => void;
}

// Map a failed send to fixed wording rather than echoing the backend's error
// text (#7721; #7131 precedent). The `code` POST /chat sends with a 502/503
// (backend/routes/chat.py) names the piece that failed and wins; otherwise
// the HTTP status decides. Only a request that got no response at all is
// "Cannot reach server".
const CHAT_CODE_MESSAGES: Record<string, string> = {
  chat_not_configured: "Chat isn't configured on this server (MCP_SERVER_URL is not set).",
  mcp_unreachable: "Chat couldn't reach its tools server (MCP). Check the MCP server is running.",
  llm_unreachable: "Chat couldn't reach its AI model. Check the model provider (e.g. Ollama) is running.",
  aws_error: "Chat's AWS call (Bedrock or MCP request signing) failed. Check the AWS credentials and access.",
};

const CHAT_STATUS_MESSAGES: Record<number, string> = {
  400: "Chat couldn't process that conversation. Please try again.",
  401: "Your session has expired. Please sign in again.",
  429: "You're sending messages too quickly. Wait a moment and try again.",
  502: "Chat couldn't reach its AI service. Please try again later.",
  503: "Chat isn't available on this server right now.",
  504: "Chat took too long to respond. Please try again.",
};

function chatErrorMessage(e: unknown): string {
  const err = e as { status?: unknown; timeout?: unknown; code?: unknown } | null;
  if (typeof err?.code === "string" && Object.hasOwn(CHAT_CODE_MESSAGES, err.code)) {
    return CHAT_CODE_MESSAGES[err.code];
  }
  if (err?.timeout) return CHAT_STATUS_MESSAGES[504];
  if (typeof err?.status === "number") {
    return CHAT_STATUS_MESSAGES[err.status] ?? "Chat ran into a server error. Please try again.";
  }
  return "Cannot reach server";
}

export function ChatPanel({ open, onClose, pages = [], context, onNavigate }: Props) {
  const messages = useChatMessages();
  const path = useChatPath();
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ index: number; draft: string } | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const saveFailed = useChatSaveFailed();
  const bottomRef = useRef<HTMLDivElement>(null);

  // Picks up the conversation saved on the server (#8870); a failure leaves
  // the local one in place and shows the "Not saved" hint.
  useEffect(() => {
    if (open) void ensureChatLoaded();
  }, [open]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages, sending]);

  if (!open) return null;

  // Posts `text` as the next user turn after `history`. `place` puts that turn
  // in the conversation; the reply is appended after it. On failure the
  // conversation is restored exactly as it was before `place`, so no
  // unanswered turn is left behind: history ending in two consecutive "user"
  // turns is rejected by the backend with a 400 (#7897).
  const submit = async (
    text: string,
    history: ChatMessage[],
    place: () => void,
    onFail?: () => void,
  ) => {
    const before = snapshotChat();
    // Not saved until the reply is in: on failure it is rolled back anyway.
    setChatReplyPending(true);
    place();
    setSending(true);
    setError(null);
    try {
      const { reply, navigate_to } = await api.postChat(text, history, pages, context);
      appendChatMessage({ role: "assistant", content: reply });
      // Only follow a path that was offered: the backend enforces this too.
      if (navigate_to && onNavigate && pages.some((page) => page.path === navigate_to)) {
        onNavigate(navigate_to);
      }
    } catch (e) {
      restoreChat(before);
      onFail?.();
      setError(chatErrorMessage(e));
    } finally {
      setSending(false);
      setChatReplyPending(false);
    }
  };

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;

    setInput("");
    // Hand the unanswered message's text back for a retry.
    await submit(
      text,
      messages,
      () => appendChatMessage({ role: "user", content: text }),
      () => setInput(text),
    );
  };

  // Adds the edited text as a new version of the message and regenerates from
  // there, sending only the turns before it as history. The old version keeps
  // its later turns, reachable through the version control (#8590, #8842).
  const saveEdit = async () => {
    if (!editing || sending) return;
    const { index } = editing;
    const node = path[index];
    const text = editing.draft.trim();
    if (!node || !text) return;
    setEditing(null);
    if (text === node.content) return;

    // On failure reopen the edit box with the edited text, so it can be retried.
    await submit(
      text,
      messages.slice(0, index),
      () => addChatVersion(node.id, { role: "user", content: text }),
      () => setEditing({ index, draft: text }),
    );
  };

  // Asks again for the reply at `index` without changing the question. The
  // new reply becomes another version of it; the old one and its later turns
  // are kept. A failure restores the old reply as the active one (#8820, #8842).
  const regenerate = async (index: number) => {
    const prompt = path[index - 1];
    if (sending || prompt?.role !== "user") return;

    setEditing(null);
    await submit(prompt.content, messages.slice(0, index - 1), () => endChatPathAt(prompt.id));
  };

  // Deletes the saved history (this conversation and every archived one). On
  // failure the conversation is kept and the error shown.
  const deleteHistory = async () => {
    setDeleting(true);
    setError(null);
    try {
      await deleteSavedChatHistory();
      setInput("");
      setEditing(null);
    } catch {
      setError("Couldn't delete your chat history. Please try again.");
    } finally {
      setDeleting(false);
      setConfirmingDelete(false);
    }
  };

  const selectVersion = (id: string, offset: number) => {
    if (sending) return;
    setEditing(null);
    selectChatVersion(id, offset);
  };

  return (
    <>
      <div
        onClick={onClose}
        style={{
          position: "fixed",
          top: 0,
          left: 0,
          width: "100%",
          height: "100%",
          background: "rgba(0,0,0,0.3)",
          zIndex: 999,
        }}
      />
      <div
        role="dialog"
        aria-label="Chat"
        style={{
          position: "fixed",
          top: 0,
          right: 0,
          width: "min(560px, 100vw)",
          height: "100%",
          boxSizing: "border-box",
          background: "var(--drawer-bg)",
          color: "var(--drawer-color)",
          borderLeft: "1px solid var(--drawer-border-color)",
          boxShadow: "-2px 0 5px rgba(0,0,0,0.3)",
          padding: "1rem",
          zIndex: 1000,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "1rem",
          }}
        >
          <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem" }}>
            <strong>Chat</strong>
            {saveFailed && (
              <span
                title="Your chat couldn't be saved to your account. It is still kept in this tab, and saving is retried on your next change."
                style={{ color: "var(--drawer-muted-color)", fontSize: "0.85em" }}
              >
                Not saved
              </span>
            )}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            {!isDemoSession() && (
              <button
                onClick={() => setConfirmingDelete(true)}
                disabled={sending || deleting || confirmingDelete}
              >
                Delete history
              </button>
            )}
            <button
              onClick={() => {
                startNewSavedChat();
                setInput("");
                setEditing(null);
                setError(null);
              }}
              disabled={sending || messages.length === 0}
            >
              New chat
            </button>
            <button
              onClick={onClose}
              aria-label="close"
              style={{
                background: "none",
                border: "none",
                fontSize: "1.2rem",
                cursor: "pointer",
              }}
            >
              ×
            </button>
          </div>
        </div>
        {confirmingDelete && (
          <div
            role="group"
            aria-label="Confirm deleting chat history"
            style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}
          >
            <span style={{ flex: "1 1 12rem" }}>
              Delete your saved chat history, including chats you started over with New chat? This can't be undone.
            </span>
            <button onClick={() => void deleteHistory()} disabled={deleting}>
              Delete
            </button>
            <button onClick={() => setConfirmingDelete(false)} disabled={deleting}>
              Cancel
            </button>
          </div>
        )}
        <div style={{ flex: 1, overflowY: "auto", marginBottom: "1rem" }}>
          {messages.length === 0 && (
            <div style={{ color: "var(--drawer-muted-color)" }}>
              Ask about your portfolios, prices, or holdings.
            </div>
          )}
          <ul
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              display: "flex",
              flexDirection: "column",
              gap: "0.75rem",
            }}
          >
            {path.map((m, i) => (
              <ChatMessageItem
                key={m.id}
                message={m}
                busy={sending}
                version={
                  m.versionCount > 1
                    ? {
                        current: m.version,
                        count: m.versionCount,
                        onSelect: (offset) => selectVersion(m.id, offset),
                      }
                    : undefined
                }
                onEdit={
                  m.role === "user" ? () => setEditing({ index: i, draft: m.content }) : undefined
                }
                onRegenerate={
                  m.role === "assistant" && path[i - 1]?.role === "user"
                    ? () => void regenerate(i)
                    : undefined
                }
                editing={
                  editing?.index === i
                    ? {
                        draft: editing.draft,
                        onChange: (draft) => setEditing({ index: i, draft }),
                        onSave: () => void saveEdit(),
                        onCancel: () => setEditing(null),
                      }
                    : undefined
                }
              />
            ))}
          </ul>
          {sending && (
            <div role="status" style={{ color: "var(--drawer-muted-color)", marginTop: "0.75rem" }}>
              Thinking…
            </div>
          )}
          {error && <div role="alert">{error}</div>}
          <div ref={bottomRef} />
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <input
            aria-label="chat message"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void send();
            }}
            style={{ flex: 1 }}
            disabled={sending}
          />
          <button onClick={() => void send()} disabled={sending || !input.trim()}>
            Send
          </button>
        </div>
      </div>
    </>
  );
}

export default ChatPanel;
