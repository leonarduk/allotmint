import { useFetch } from "../hooks/useFetch";
import * as api from "../api";
import type { Alert } from "../types";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function NotificationsDrawer({ open, onClose }: Props) {
  const { data: alerts, loading, error } = useFetch<Alert[]>(
    api.getAlerts,
    [],
    open,
  );

  const alertList = alerts ?? [];

  if (!open) return null;

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
          width: "300px",
          height: "100%",
          background: "#fff",
          borderLeft: "1px solid #ccc",
          boxShadow: "-2px 0 5px rgba(0,0,0,0.3)",
          padding: "1rem",
          zIndex: 1000,
          overflowY: "auto",
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
          <strong>Alerts</strong>
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
        {loading && <div>Loading...</div>}
        {error && <div>Cannot reach server</div>}
        {!loading && !error && alertList.length === 0 && <div>No alerts</div>}
        {!loading && !error && alertList.length > 0 && (
          <ul style={{ listStyle: "none", padding: 0 }}>
            {alertList.map((a, i) => (
              <li key={i} style={{ marginBottom: "0.5rem" }}>
                <div>
                  <strong>{a.ticker}</strong>: {a.message}
                </div>
                <div style={{ fontSize: "0.8rem", color: "#666" }}>
                  {new Date(a.timestamp).toLocaleString()}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}

export default NotificationsDrawer;

