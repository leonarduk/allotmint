import { useFetch } from "../hooks/useFetch";
import * as api from "../api";
import type { Alert, Nudge } from "../types";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function NotificationsDrawer({ open, onClose }: Props) {
  const {
    data: alerts,
    loading: alertLoading,
    error: alertError,
  } = useFetch<Alert[]>(api.getAlerts, [], open);
  const {
    data: nudges,
    loading: nudgeLoading,
    error: nudgeError,
  } = useFetch<Nudge[]>(api.getNudges, [], open);
  const alertList = alerts ?? [];
  const nudgeList = nudges ?? [];

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
        {alertLoading && <div>Loading...</div>}
        {alertError && <div>Cannot reach server</div>}
        {!alertLoading && !alertError && alertList.length === 0 && <div>No alerts</div>}
        {!alertLoading && !alertError && alertList.length > 0 && (
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
        <div style={{ marginTop: "1rem" }}>
          <strong>Nudges</strong>
        </div>
        {nudgeLoading && <div>Loading...</div>}
        {nudgeError && <div>Cannot reach server</div>}
        {!nudgeLoading && !nudgeError && nudgeList.length === 0 && <div>No nudges</div>}
        {!nudgeLoading && !nudgeError && nudgeList.length > 0 && (
          <ul style={{ listStyle: "none", padding: 0 }}>
            {nudgeList.map((n) => (
              <li key={n.id} style={{ marginBottom: "0.5rem" }}>
                <div>{n.message}</div>
                <div style={{ fontSize: "0.8rem", color: "#666" }}>
                  {new Date(n.timestamp).toLocaleString()}
                </div>
                <div style={{ marginTop: "0.25rem" }}>
                  <button onClick={() => api.snoozeNudges(n.id, 1)}>Snooze</button>
                  <select
                    defaultValue={7}
                    onChange={(e) =>
                      api.subscribeNudges(n.id, Number(e.target.value))
                    }
                    style={{ marginLeft: "0.5rem" }}
                  >
                    <option value={1}>Daily</option>
                    <option value={3}>Every 3 days</option>
                    <option value={7}>Weekly</option>
                  </select>
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

