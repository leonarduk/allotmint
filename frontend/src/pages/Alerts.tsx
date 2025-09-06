import { useEffect, useState } from 'react';
import * as api from '../api';
import type { Alert } from '../types';

export default function Alerts() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getAlerts()
      .then(setAlerts)
      .catch(() => setAlerts([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading)
    return (
      <div role="status" aria-live="polite">
        Loading...
      </div>
    );
  if (alerts.length === 0)
    return (
      <div role="status" aria-live="polite">
        No alerts.
      </div>
    );

  return (
    <ul aria-live="polite" style={{ margin: 0, paddingLeft: '1.2rem' }}>
      {alerts.map((a, i) => (
        <li key={i}>
          <strong>{a.ticker}</strong>: {a.message}
        </li>
      ))}
    </ul>
  );
}
