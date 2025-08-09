import { useState } from "react";
import { API_BASE } from "../api";

export default function Support() {
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState<string | null>(null);

  const envEntries = Object.entries(import.meta.env).sort();
  const online = typeof navigator !== "undefined" ? navigator.onLine : true;

  async function send() {
    setStatus("sending");
    try {
      const res = await fetch(`${API_BASE}/support/telegram`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: message }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setStatus("sent");
      setMessage("");
    } catch {
      setStatus("error");
    }
  }

  return (
    <div style={{ maxWidth: 600, margin: "0 auto", padding: "1rem" }}>
      <h1>Support</h1>
      <p>
        <strong>Online:</strong> {online ? "yes" : "no"}
      </p>
      <h2>Environment</h2>
      <table style={{ fontSize: "0.9rem" }}>
        <tbody>
          {envEntries.map(([k, v]) => (
            <tr key={k}>
              <td style={{ paddingRight: "0.5rem", fontWeight: 500 }}>{k}</td>
              <td>{String(v)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h2>Telegram Message</h2>
      <textarea
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        rows={4}
        style={{ width: "100%" }}
      />
      <div style={{ marginTop: "0.5rem" }}>
        <button onClick={send} disabled={!message}>
          Send
        </button>
        {status === "sent" && (
          <span style={{ marginLeft: "0.5rem", color: "green" }}>Sent</span>
        )}
        {status === "error" && (
          <span style={{ marginLeft: "0.5rem", color: "red" }}>
            Failed to send
          </span>
        )}
        {status === "sending" && (
          <span style={{ marginLeft: "0.5rem" }}>Sending…</span>
        )}
      </div>
    </div>
  );
}
