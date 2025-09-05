import React from "react";

interface Props {
  onRetry?: () => void;
}

export default function BackendUnavailableCard({ onRetry }: Props) {
  return (
    <div
      style={{
        maxWidth: 400,
        margin: "2rem auto",
        padding: "1rem",
        border: "1px solid #ccc",
        borderRadius: "8px",
        textAlign: "center",
      }}
    >
      <h2>Backend unavailable</h2>
      <p style={{ color: "#555", marginBottom: "1rem" }}>
        The backend service could not be reached. You can retry or open a
        cached read-only view.
      </p>
      <div style={{ marginBottom: "1rem" }}>
        <button onClick={onRetry} disabled={!onRetry}>
          Retry
        </button>
      </div>
      <div style={{ fontSize: "0.9rem" }}>
        <a
          href="/snapshots/index.html"
          target="_blank"
          rel="noopener noreferrer"
          style={{ marginRight: "0.5rem" }}
        >
          Cached view
        </a>
        <a
          href="/offline"
          target="_blank"
          rel="noopener noreferrer"
        >
          Read-only mode
        </a>
      </div>
    </div>
  );
}
