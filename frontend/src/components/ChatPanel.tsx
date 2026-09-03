import { useState } from "react";
import * as api from "../api";
import type { ChatMessage } from "../api";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function ChatPanel({ open, onClose }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    } catch {
      setError("Cannot reach server");
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
        style={{
          position: "fixed",
          top: 0,
          right: 0,
          width: "320px",
          height: "100%",
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
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {messages.map((m, i) => (
              <li key={i} style={{ marginBottom: "0.5rem" }}>
                <strong>{m.role === "user" ? "You" : "Assistant"}:</strong> {m.content}
              </li>
            ))}
          </ul>
          {error && <div role="alert">{error}</div>}
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
