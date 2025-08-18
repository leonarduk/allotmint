import { getAlerts, getAlertSettings, setAlertSettings } from "../api";
import type { Alert } from "../types";
import { useFetch } from "../hooks/useFetch";
import { useEffect, useState } from "react";
export function AlertsPanel({ user = "default" }: { user?: string }) {
  const { data: alerts, loading, error } = useFetch<Alert[]>(getAlerts, []);
  const [threshold, setThreshold] = useState<number>();

  useEffect(() => {
    getAlertSettings(user).then((r) => setThreshold(r.threshold));
  }, [user]);

  const save = () => {
    if (threshold !== undefined) setAlertSettings(user, threshold);
  };

  if (loading || error || !alerts) return null;

  const importAlert = alerts.find((a) => a.ticker === "TRADES");
  const otherAlerts = alerts.filter((a) => a.ticker !== "TRADES");

  if (!importAlert && otherAlerts.length === 0) return null;

  return (
    <div style={{ border: "1px solid #ccc", padding: "0.5rem", marginBottom: "1rem" }}>
      <strong>Alerts</strong>
      {importAlert && (
        <div style={{ marginTop: "0.5rem" }}>
          <em>{importAlert.message}</em>
        </div>
      )}
      <div style={{ marginTop: "0.5rem" }}>
        <label>
          Threshold %:{" "}
          <input
            type="number"
            value={threshold ?? ""}
            onChange={(e) => setThreshold(parseFloat(e.target.value))}
            style={{ width: "4rem" }}
          />
        </label>
        <button onClick={save} style={{ marginLeft: "0.5rem" }}>
          Save
        </button>
      </div>
      {otherAlerts.length > 0 && (
        <ul style={{ margin: 0, paddingLeft: "1.2rem" }}>
          {otherAlerts.map((a, i) => (
            <li key={i}>
              <strong>{a.ticker}</strong>: {a.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
