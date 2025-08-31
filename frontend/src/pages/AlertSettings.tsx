import { useEffect, useState } from "react";
import { getAlertThreshold, setAlertThreshold } from "../api";

export function AlertSettings() {
  const [user, setUser] = useState("");
  const [threshold, setThreshold] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    setLoading(true);
    getAlertThreshold(user)
      .then((res) => {
        setThreshold(String(res.threshold));
        setMessage(null);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [user]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const value = parseFloat(threshold);
    if (!user || Number.isNaN(value)) return;
    setLoading(true);
    try {
      await setAlertThreshold(user, value);
      setMessage("Saved");
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setMessage(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ maxWidth: "20rem" }}>
      <div style={{ marginBottom: "0.5rem" }}>
        <label>
          User:
          <input
            value={user}
            onChange={(e) => setUser(e.target.value)}
            style={{ marginLeft: "0.5rem", width: "100%" }}
          />
        </label>
      </div>
      <div style={{ marginBottom: "0.5rem" }}>
        <label>
          Threshold:
          <input
            type="number"
            step="0.01"
            value={threshold}
            onChange={(e) => setThreshold(e.target.value)}
            style={{ marginLeft: "0.5rem", width: "100%" }}
          />
        </label>
      </div>
      <button type="submit" disabled={loading || !user}>
        Save
      </button>
      {message && <div style={{ color: "green" }}>{message}</div>}
      {error && <div style={{ color: "red" }}>{error}</div>}
    </form>
  );
}

export default AlertSettings;

