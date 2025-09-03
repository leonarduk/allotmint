import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { toast } from "react-toastify";
import * as api from "../api";
import type { Alert } from "../types";
import { useFetch } from "../hooks/useFetch";

export function AlertsPanel() {
  const { data: alerts } = useFetch<Alert[]>(api.getAlerts, []);
  const shown = useRef(new Set<string>());

  useEffect(() => {
    alerts?.forEach((a) => {
      const key = `${a.ticker}:${a.message}`;
      if (!shown.current.has(key)) {
        shown.current.add(key);
        toast(`${a.ticker}: ${a.message}`);
      }
    });
  }, [alerts]);

  return (
    <div style={{ marginBottom: "1rem" }}>
      <Link to="/alerts">View all alerts</Link>
    </div>
  );
}
