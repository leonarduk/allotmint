import { useEffect, useRef, useState } from "react";
import * as api from "../api";
import type { ChatContext, ChatMessage, ChatPage } from "../api";
import {
  appendChatMessage,
  setChatMessages,
  startNewChat,
  useChatMessages,
} from "../utils/chatConversation";
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
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ index: number; draft: string } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages, sending]);

  if (!open) return null;

  // Posts `text` as the next user turn after `history`. `onFail` puts the
  // conversation back: an unanswered message left in `messages` would make the
  // next send's history end in two consecutive "user" turns, which the backend
  // rejects with a 400 (#7897).
  const submit = async (text: string, history: ChatMessage[], onFail: () => void) => {
    setChatMessages([...history, { role: "user", content: text }]);
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
      onFail();
      setError(chatErrorMessage(e));
    } finally {
      setSending(false);
    }
  };

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;

    const history = messages;
    setInput("");
    // Drop the unanswered message and hand its text back for a retry.
    await submit(text, history, () => {
      setChatMessages(history);
      setInput(text);
    });
  };

  // Replaces the edited message and regenerates from there: every later turn
  // is discarded and only the turns before it are sent as history (#8590).
  const saveEdit = async () => {
    if (!editing || sending) return;
    const { index } = editing;
    const text = editing.draft.trim();
    if (!text) return;
    setEditing(null);
    if (text === messages[index]?.content) return;

    const previous = messages;
    // On failure restore the pre-edit conversation and reopen the edit box
    // with the edited text, so it can be retried.
    await submit(text, messages.slice(0, index), () => {
      setChatMessages(previous);
      setEditing({ index, draft: text });
    });
  };

  // Asks again for the reply at `index` without changing the question: that
  // reply and every later turn are discarded, and the preceding user message
  // is resent with only the turns before it as history (#8820).
  const regenerate = async (index: number) => {
    const prompt = messages[index - 1];
    if (sending || prompt?.role !== "user") return;

    const previous = messages;
    setEditing(null);
    // On failure restore the conversation as it was, old reply included, so
    // a failed regenerate never loses the answer the user already had.
    await submit(prompt.content, messages.slice(0, index - 1), () => setChatMessages(previous));
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
          <strong>Chat</strong>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <button
              onClick={() => {
                startNewChat();
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
            {messages.map((m, i) => (
              <ChatMessageItem
                key={i}
                message={m}
                busy={sending}
                onEdit={
                  m.role === "user" ? () => setEditing({ index: i, draft: m.content }) : undefined
                }
                onRegenerate={
                  m.role === "assistant" && messages[i - 1]?.role === "user"
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
