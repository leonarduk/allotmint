import * as api from "../api";
import type { Alert } from "../types";
import { useFetch } from "../hooks/useFetch";
import { useEffect, useState } from "react";
import { AlertsTicker } from "./AlertsTicker";
export function AlertsPanel({ user = "default" }: { user?: string }) {
  const { data: alerts, loading, error } = useFetch<Alert[]>(api.getAlerts, []);
  const [threshold, setThreshold] = useState<number>();
  const [settingsError, setSettingsError] = useState(false);

  useEffect(() => {
    if (api.getAlertSettings) {
      api
        .getAlertSettings(user)
        .then((r) => setThreshold(r.threshold))
        .catch(() => setSettingsError(true));
    }
  }, [user]);

  const save = () => {
    if (threshold !== undefined && api.setAlertSettings) {
      api.setAlertSettings(user, threshold);
    }
  };

  if (loading) return null;

  if (error || settingsError) {
    return (
      <div style={{ border: "1px solid #ccc", padding: "0.5rem", marginBottom: "1rem" }}>
        Cannot reach server
      </div>
    );
  }

  const importAlert = alerts?.find((a) => a.ticker === "IMPORT");
  const otherAlerts = alerts?.filter((a) => a.ticker !== "IMPORT") ?? [];

  const lowPriorityAlerts =
    threshold !== undefined
      ? otherAlerts.filter((a) => a.change_pct < threshold)
      : [];
  const highPriorityAlerts =
    threshold !== undefined
      ? otherAlerts.filter((a) => a.change_pct >= threshold)
      : otherAlerts;

  if (!importAlert && otherAlerts.length === 0) return null;

  return (
    <div style={{ border: "1px solid #ccc", padding: "0.5rem", marginBottom: "1rem" }}>
      <strong>Alerts</strong>
      {importAlert && (
        <div data-testid="import-status" style={{ marginTop: "0.5rem" }}>
          {importAlert.message}
        </div>
      )}
      {otherAlerts.length > 0 && (
        <>
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
          {highPriorityAlerts.length > 0 && (
            <ul style={{ margin: 0, paddingLeft: "1.2rem" }}>
              {highPriorityAlerts.map((a, i) => (
                <li key={i}>
                  <strong>{a.ticker}</strong>: {a.message}
                </li>
              ))}
            </ul>
          )}
          {lowPriorityAlerts.length > 0 && (
            <AlertsTicker alerts={lowPriorityAlerts} speed={30} pauseOnHover />
          )}
        </>
      )}
    </div>
  );
}
