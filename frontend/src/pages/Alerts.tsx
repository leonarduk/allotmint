import { useEffect, useState } from "react";
import * as api from "../api";
import type { Alert } from "../types";
import errorToast from "../utils/errorToast";

export default function Alerts() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const timeout = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error("timeout")), 5000),
    );

    Promise.race([api.getAlerts(), timeout])
      .then((res) => {
        if (!cancelled) setAlerts(res);
      })
      .catch((e) => {
        if (!cancelled) {
          setAlerts([]);
          setError(
            navigator.onLine
              ? "Request timed out. Please try again."
              : "You appear to be offline.",
          );
          errorToast(e);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) return <div>Loading...</div>;
  if (error) return <div>{error}</div>;
  if (alerts.length === 0) return <div>No alerts.</div>;

  return (
    <ul style={{ margin: 0, paddingLeft: "1.2rem" }}>
      {alerts.map((a, i) => (
        <li key={i}>
          <strong>{a.ticker}</strong>: {a.message}
        </li>
      ))}
    </ul>
  );
}
