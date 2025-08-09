import { useEffect, useState } from "react";
import { getAlerts } from "../api";
import type { Alert } from "../types";

export function AlertsPanel() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  useEffect(() => {
    getAlerts().then(setAlerts).catch(() => setAlerts([]));
  }, []);
  if (!alerts.length) return null;
  return (
    <div style={{ border: "1px solid #ccc", padding: "0.5rem", marginBottom: "1rem" }}>
      <strong>Alerts</strong>
      <ul style={{ margin: 0, paddingLeft: "1.2rem" }}>
        {alerts.map((a, i) => (
          <li key={i}>
            <strong>{a.ticker}</strong>: {a.message}
          </li>
        ))}
      </ul>
    </div>
  );
}
