import { useEffect, useState } from "react";
import { getConfig, updateConfig } from "../api";

export default function AdminConfig() {
  const [config, setConfig] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    getConfig().then((data) => {
      const entries: Record<string, string> = {};
      Object.entries(data).forEach(([k, v]) => {
        entries[k] = v == null ? "" : String(v);
      });
      setConfig(entries);
    });
  }, []);

  function handleChange(key: string, value: string) {
    setConfig((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("saving");
    const payload: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(config)) {
      let parsed: unknown = v;
      try {
        parsed = JSON.parse(v);
      } catch {
        // keep as string
      }
      payload[k] = parsed;
    }
    try {
      await updateConfig(payload);
      const fresh = await getConfig();
      const entries: Record<string, string> = {};
      Object.entries(fresh).forEach(([k, v]) => {
        entries[k] = v == null ? "" : String(v);
      });
      setConfig(entries);
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  if (!Object.keys(config).length) {
    return <p>Loading…</p>;
  }

  return (
    <form
      onSubmit={handleSubmit}
      style={{ maxWidth: 600, margin: "0 auto", padding: "1rem" }}
    >
      <h1>Admin Config</h1>
      {Object.entries(config).map(([key, value]) => (
        <div key={key} style={{ marginBottom: "0.5rem" }}>
          <label style={{ display: "block", fontWeight: 500 }}>
            {key}
          </label>
          <input
            type="text"
            value={value}
            onChange={(e) => handleChange(key, e.target.value)}
            style={{ width: "100%" }}
          />
        </div>
      ))}
      <button type="submit">Save</button>
      {status === "saved" && (
        <span style={{ marginLeft: "0.5rem", color: "green" }}>Saved</span>
      )}
      {status === "error" && (
        <span style={{ marginLeft: "0.5rem", color: "red" }}>Error</span>
      )}
      {status === "saving" && (
        <span style={{ marginLeft: "0.5rem" }}>Saving…</span>
      )}
    </form>
  );
}
