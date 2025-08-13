import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { API_BASE, getConfig, updateConfig } from "../api";

export default function Support() {
  const { t } = useTranslation();
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [config, setConfig] = useState<Record<string, string | boolean>>({});
  const [configStatus, setConfigStatus] = useState<string | null>(null);

  const envEntries = Object.entries(import.meta.env).sort();
  const online = typeof navigator !== "undefined" ? navigator.onLine : true;

  useEffect(() => {
    getConfig()
      .then((cfg) => {
        const entries: Record<string, string | boolean> = {};
        Object.entries(cfg).forEach(([k, v]) => {
          entries[k] = typeof v === "boolean" ? v : v == null ? "" : String(v);
        });
        setConfig(entries);
      })
      .catch(() => {
        /* ignore */
      });
  }, []);

  function handleConfigChange(key: string, value: string | boolean) {
    setConfig((prev) => ({ ...prev, [key]: value }));
  }

  async function saveConfig(e: React.FormEvent) {
    e.preventDefault();
    setConfigStatus("saving");
    const payload: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(config)) {
      if (typeof v === "string") {
        let parsed: unknown = v;
        try {
          parsed = JSON.parse(v);
        } catch {
          /* keep as string */
        }
        payload[k] = parsed;
      } else {
        payload[k] = v;
      }
    }
    try {
      await updateConfig(payload);
      const fresh = await getConfig();
      const entries: Record<string, string | boolean> = {};
      Object.entries(fresh).forEach(([k, v]) => {
        entries[k] = typeof v === "boolean" ? v : v == null ? "" : String(v);
      });
      setConfig(entries);
      setConfigStatus("saved");
    } catch {
      setConfigStatus("error");
    }
  }

  async function send() {
    setStatus("sending");
    try {
      const res = await fetch(`${API_BASE}/support/telegram`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: message }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setStatus("sent");
      setMessage("");
    } catch {
      setStatus("error");
    }
  }

  return (
    <div style={{ maxWidth: 600, margin: "0 auto", padding: "1rem" }}>
      <h1>{t("support.title")}</h1>
      <p>
        <strong>{t("support.online")}</strong> {online ? t("support.onlineYes") : t("support.onlineNo")}
      </p>
      <h2>{t("support.environment")}</h2>
      <table style={{ fontSize: "0.9rem" }}>
        <tbody>
          {envEntries.map(([k, v]) => {
            const value = String(v);
            if (k === "VITE_API_URL") {
              const base = value.replace(/\/$/, "");
              return (
                <tr key={k}>
                  <td style={{ paddingRight: "0.5rem", fontWeight: 500 }}>{k}</td>
                  <td>
                    <a href={value}>{value}</a>{" "}
                    <a href={`${base}/docs#/`}>swagger</a>
                  </td>
                </tr>
              );
            }
            return (
              <tr key={k}>
                <td style={{ paddingRight: "0.5rem", fontWeight: 500 }}>{k}</td>
                <td>{value}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <h2>Configuration</h2>
      {!Object.keys(config).length ? (
        <p>Loading…</p>
      ) : (
        <form onSubmit={saveConfig}>
          {Object.entries(config).map(([key, value]) => (
            <div key={key} style={{ marginBottom: "0.5rem" }}>
              <label style={{ display: "block", fontWeight: 500 }}>{key}</label>
              {key === "theme" && typeof value === "string" ? (
                <div>
                  {(["dark", "light", "system"] as const).map((opt) => (
                    <label key={opt} style={{ marginRight: "0.5rem" }}>
                      <input
                        type="radio"
                        name="theme"
                        value={opt}
                        checked={value === opt}
                        onChange={(e) => handleConfigChange(key, e.target.value)}
                      />
                      {opt}
                    </label>
                  ))}
                </div>
              ) : typeof value === "boolean" ? (
                <select
                  value={String(value)}
                  onChange={(e) => handleConfigChange(key, e.target.value === "true")}
                >
                  <option value="true">true</option>
                  <option value="false">false</option>
                </select>
              ) : (
                <input
                  type="text"
                  value={String(value ?? "")}
                  onChange={(e) => handleConfigChange(key, e.target.value)}
                  style={{ width: "100%" }}
                />
              )}
            </div>
          ))}
          <button type="submit">Save</button>
          {configStatus === "saved" && (
            <span style={{ marginLeft: "0.5rem", color: "green" }}>Saved</span>
          )}
          {configStatus === "error" && (
            <span style={{ marginLeft: "0.5rem", color: "red" }}>Error</span>
          )}
          {configStatus === "saving" && (
            <span style={{ marginLeft: "0.5rem" }}>Saving…</span>
          )}
        </form>
      )}
      <h2>{t("support.telegramMessage")}</h2>
      <textarea
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        rows={4}
        style={{ width: "100%" }}
      />
      <div style={{ marginTop: "0.5rem" }}>
        <button onClick={send} disabled={!message}>
          {t("support.send")}
        </button>
        {status === "sent" && (
          <span style={{ marginLeft: "0.5rem", color: "green" }}>{t("support.status.sent")}</span>
        )}
        {status === "error" && (
          <span style={{ marginLeft: "0.5rem", color: "red" }}>
            {t("support.status.error")}
          </span>
        )}
        {status === "sending" && (
          <span style={{ marginLeft: "0.5rem" }}>{t("support.status.sending")}</span>
        )}
      </div>
    </div>
  );
}
