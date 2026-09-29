import { useEffect, useRef, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import * as api from "../api";
import type { ChatMessage, ChatPage } from "../api";

interface Props {
  open: boolean;
  onClose: () => void;
  /** Pages the assistant may open for the user. */
  pages?: ChatPage[];
  /** Called with a page's path when the assistant opens it. */
  onNavigate?: (path: string) => void;
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

export function ChatPanel({ open, onClose, pages = [], onNavigate }: Props) {
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
      const { reply, navigate_to } = await api.postChat(text, history, pages);
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
      // Only follow a path that was offered: the backend enforces this too.
      if (navigate_to && onNavigate && pages.some((page) => page.path === navigate_to)) {
        onNavigate(navigate_to);
      }
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
