import { useEffect, useRef, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import * as api from "../api";
import type { ChatMessage } from "../api";

interface Props {
  open: boolean;
  onClose: () => void;
}

// Assistant replies are Markdown (headings, bold, GFM tables). Raw HTML is not
// rendered (react-markdown's default), so model output cannot inject markup.
const markdownComponents: Components = {
  table: ({ children }) => (
    <div className="chat-markdown-table">
      <table>{children}</table>
    </div>
  ),
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
};

// Prefer the backend's explanation (chat not configured, MCP server or LLM
// down) over a generic message; only a request that got no response at all
// is "Cannot reach server".
function chatErrorMessage(e: unknown): string {
  const err = e as { detail?: unknown; status?: unknown; timeout?: unknown; message?: string } | null;
  if (typeof err?.detail === "string" && err.detail) return err.detail;
  if ((typeof err?.status === "number" || err?.timeout) && err.message) return err.message;
  return "Cannot reach server";
}

function ChatMessageItem({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <li
      aria-label={isUser ? "You" : "Assistant"}
      style={{
        alignSelf: isUser ? "flex-end" : "stretch",
        maxWidth: isUser ? "85%" : "100%",
        background: isUser ? "var(--chat-user-bg)" : "var(--chat-assistant-bg)",
        border: "1px solid var(--drawer-border-color)",
        borderRadius: "0.5rem",
        padding: "0.5rem 0.75rem",
        whiteSpace: isUser ? "pre-wrap" : undefined,
        overflowWrap: "anywhere",
      }}
    >
      {isUser ? (
        message.content
      ) : (
        <div className="chat-markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {message.content}
          </ReactMarkdown>
        </div>
      )}
    </li>
  );
}

export function ChatPanel({ open, onClose }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages, sending]);

  if (!open) return null;

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;

    const history = messages;
    const userMessage: ChatMessage = { role: "user", content: text };
    setMessages([...history, userMessage]);
    setInput("");
    setSending(true);
    setError(null);
    try {
      const { reply } = await api.postChat(text, history);
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
    } catch (e) {
      // Drop the unanswered message and hand its text back for a retry: left
      // in `messages`, it would make the next send's history end in two
      // consecutive "user" turns, which the backend rejects with a 400 (#7897).
      setMessages(history);
      setInput(text);
      setError(chatErrorMessage(e));
    } finally {
      setSending(false);
    }
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
              <ChatMessageItem key={i} message={m} />
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
