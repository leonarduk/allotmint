import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  API_BASE,
  getConfig,
  getOwners,
  updateConfig,
  savePushSubscription,
  deletePushSubscription,
  checkPortfolioHealth,
  type Finding,
  refreshPrices,
} from "../api";
import { useConfig } from "../ConfigContext";
import { OwnerSelector } from "../components/OwnerSelector";
import SectionCard from "../components/SectionCard";
import type { OwnerSummary } from "../types";
import { orderedTabPlugins, type TabPluginId } from "../tabPlugins";
import { usePriceRefresh } from "../PriceRefreshContext";

const TAB_KEYS = orderedTabPlugins.map((p) => p.id) as TabPluginId[];
const EMPTY_TABS = Object.fromEntries(TAB_KEYS.map((k) => [k, false])) as Record<
  TabPluginId,
  boolean
>;

const UI_KEYS = new Set(["theme", "relative_view_enabled"]);

type ConfigValue = string | boolean | Record<string, unknown>;
type ConfigState = Record<string, ConfigValue>;

export default function Support() {
  const { t } = useTranslation();
  const { refreshConfig } = useConfig();
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [config, setConfig] = useState<ConfigState>({});
  const [tabs, setTabs] = useState<Record<TabPluginId, boolean>>(EMPTY_TABS);
  const [configStatus, setConfigStatus] = useState<string | null>(null);
  const [pushEnabled, setPushEnabled] = useState(false);
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [owner, setOwner] = useState("");
  const [pushStatus, setPushStatus] = useState<string | null>(null);
  const [health, setHealth] = useState<Finding[]>([]);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [healthRunning, setHealthRunning] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [logs, setLogs] = useState("");
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState<string | null>(null);
  const { lastRefresh, setLastRefresh } = usePriceRefresh();

  const envEntries = Object.entries(import.meta.env).sort();
  const online = typeof navigator !== "undefined" ? navigator.onLine : true;

  useEffect(() => {
    getOwners()
      .then((list) => {
        setOwners(list);
        setOwner(list[0]?.owner ?? "");
      })
      .catch(() => setOwners([]));
  }, []);

  useEffect(() => {
    getConfig()
      .then((cfg) => {
        const entries: ConfigState = {};
        Object.entries(cfg).forEach(([k, v]) => {
          if (v && typeof v === "object" && !Array.isArray(v)) {
            entries[k] = v as Record<string, unknown>;
          } else {
            entries[k] = typeof v === "boolean" ? v : v == null ? "" : String(v);
          }
        });
        setConfig(entries);
        const tabConfig =
          cfg && typeof cfg === "object" && cfg.tabs && typeof cfg.tabs === "object"
            ? (cfg.tabs as Record<string, unknown>)
            : {};
        setTabs(
          TAB_KEYS.reduce(
            (acc, key) => ({ ...acc, [key]: Boolean(tabConfig[key]) }),
            { ...EMPTY_TABS },
          ),
        );
      })
      .catch(() => {
        /* ignore */
      });
  }, []);

  useEffect(() => {
    if (
      typeof navigator !== "undefined" &&
      navigator.serviceWorker &&
      "ready" in navigator.serviceWorker
    ) {
      navigator.serviceWorker.ready
        .then((reg) => reg.pushManager.getSubscription())
        .then((sub) => setPushEnabled(!!sub))
        .catch(() => {
          /* ignore */
        });
    }
  }, []);

  function handleConfigChange(key: string, value: string | boolean) {
    setConfig((prev) => ({ ...prev, [key]: value }));
  }

  function handleTabChange(key: TabPluginId, value: boolean) {
    setTabs((prev) => ({ ...prev, [key]: value }));
  }

  async function runHealthCheck() {
    setHealthRunning(true);
    setHealthError(null);
    try {
      const res = await checkPortfolioHealth();
      setHealth(res.findings);
    } catch {
      setHealthError(t("support.health.error"));
      setHealth([]);
    } finally {
      setHealthRunning(false);
    }
  }

  async function copyReport() {
    try {
      await navigator.clipboard.writeText(
        JSON.stringify(health, null, 2),
      );
    } catch {
      /* ignore */
    }
  }

  async function handleRefreshPrices() {
    setRefreshing(true);
    setRefreshError(null);
    try {
      const resp = await refreshPrices();
      setLastRefresh(resp.timestamp ?? new Date().toISOString());
    } catch (e) {
      setRefreshError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  }

  const loadLogs = useCallback(async () => {
    setLogsLoading(true);
    setLogsError(null);
    try {
      const res = await fetch(`${API_BASE}/logs`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const text = await res.text();
      setLogs(text);
    } catch {
      setLogs("");
      setLogsError(t("support.logs.error"));
    } finally {
      setLogsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadLogs().catch(() => {
      /* error handled in loadLogs */
    });
  }, [loadLogs]);

  async function saveConfig(e: React.FormEvent) {
    e.preventDefault();
    setConfigStatus("saving");
    const payload: Record<string, unknown> = {};
    const ui: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(config)) {
      if (k === "tabs") continue; // rebuilt from toggle state
      if (UI_KEYS.has(k)) {
        const parsedVal = (() => {
          if (typeof v === "string") {
            try {
              return JSON.parse(v);
            } catch {
              return v;
            }
          }
          return v;
        })();
        ui[k] = parsedVal;
        continue;
      }
      const parsedVal = (() => {
        if (typeof v === "string") {
          try {
            return JSON.parse(v);
          } catch {
            return v;
          }
        }
        return v;
      })();
      if (k === "relative_view_enabled" || k === "theme") {
        ui[k] = parsedVal;
      } else {
        payload[k] = parsedVal;
      }
    }
    ui.tabs = { ...tabs };
    if (Object.keys(ui).length) {
      payload.ui = ui;
    }
    try {
      await updateConfig(payload);
      await refreshConfig();
      const fresh = await getConfig();
      const entries: ConfigState = {};
      Object.entries(fresh).forEach(([k, v]) => {
        if (v && typeof v === "object" && !Array.isArray(v)) {
          entries[k] = v as Record<string, unknown>;
        } else {
          entries[k] = typeof v === "boolean" ? v : v == null ? "" : String(v);
        }
      });
      setConfig(entries);
      const freshTabs =
        fresh && typeof fresh === "object" && fresh.tabs && typeof fresh.tabs === "object"
          ? (fresh.tabs as Record<string, unknown>)
          : {};
      setTabs(
        TAB_KEYS.reduce(
          (acc, key) => ({ ...acc, [key]: Boolean(freshTabs[key]) }),
          { ...EMPTY_TABS },
        ),
      );
      setConfigStatus("saved");
    } catch {
      setConfigStatus("error");
    }
  }

  function urlBase64ToUint8Array(base64String: string) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const rawData = atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  async function enablePush() {
    if (!owner) return;
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setPushStatus("denied");
        return;
      }
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: import.meta.env.VITE_VAPID_PUBLIC_KEY
          ? urlBase64ToUint8Array(import.meta.env.VITE_VAPID_PUBLIC_KEY as string)
          : undefined,
      });
      await savePushSubscription(
        owner,
        sub.toJSON() as import("../api").PushSubscriptionJSON,
      );
      setPushEnabled(true);
      setPushStatus("enabled");
    } catch {
      setPushStatus("error");
    }
  }

  async function disablePush() {
    if (!owner) return;
    try {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      if (sub) await sub.unsubscribe();
      await deletePushSubscription(owner);
      setPushEnabled(false);
      setPushStatus("disabled");
    } catch {
      setPushStatus("error");
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
    <div className="container mx-auto max-w-3xl space-y-8 p-4">
      <header>
        <Link
          to="/"
          className="mb-2 inline-block text-blue-500 hover:underline"
        >
          {t("app.userLink")}
        </Link>
        <h1 className="mb-1 text-2xl font-bold md:text-4xl">
          {t("support.title")}
        </h1>
        <p>
          <strong>{t("support.online")}</strong>{" "}
          {online ? t("support.onlineYes") : t("support.onlineNo")}
        </p>
      </header>

      <SectionCard title={t("support.environment")} items={envEntries}>
        <table className="w-full table-auto text-sm">
          <tbody>
            {envEntries.map(([k, v]) => {
              const value = String(v);
              if (k === "VITE_API_URL") {
                const base = value.replace(/\/$/, "");
                return (
                  <tr key={k} className="odd:bg-black/10">
                    <td className="pr-2 font-medium">{k}</td>
                    <td>
                      <a href={value}>{value}</a>{" "}
                      <a href={`${base}/docs#/`}>swagger</a>
                    </td>
                  </tr>
                );
              }
              return (
                <tr key={k} className="odd:bg-black/10">
                  <td className="pr-2 font-medium">{k}</td>
                  <td>{value}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </SectionCard>

      <SectionCard title={t("support.logs.title")}>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => {
              loadLogs().catch(() => {
                /* error handled in loadLogs */
              });
            }}
            disabled={logsLoading}
            className="rounded bg-blue-600 px-3 py-1 text-sm font-medium text-white disabled:opacity-50"
          >
            {logsLoading ? t("common.loading") : t("support.logs.refresh")}
          </button>
          {logsError && (
            <span className="text-sm text-red-600" role="status">
              {logsError}
            </span>
          )}
        </div>
        <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded bg-black/5 p-3 text-xs">
          {logs ? logs : t("support.logs.empty")}
        </pre>
      </SectionCard>

      <SectionCard title={t("support.priceRefresh")}> 
        <button
          type="button"
          onClick={handleRefreshPrices}
          disabled={refreshing}
          className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
        >
          {refreshing ? t("app.refreshing") : t("app.refreshPrices")}
        </button>
        {lastRefresh && (
          <span className="ml-2 text-sm text-gray-600">
            {t("app.last")} {new Date(lastRefresh).toLocaleString()}
          </span>
        )}
        {refreshError && (
          <span className="ml-2 text-sm text-red-600">{refreshError}</span>
        )}
      </SectionCard>

      <SectionCard title={t("support.health.title")} items={health}>
        <button
          type="button"
          onClick={runHealthCheck}
          disabled={healthRunning}
          className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
        >
          {t("support.health.run")}
        </button>
        {healthError && <p role="alert">{healthError}</p>}
        {health.length > 0 && (
          <div className="mt-2 space-y-2">
            <ul>
              {health.map((f, idx) => (
                <li
                  key={idx}
                  className={
                    f.level === "error"
                      ? "text-red-600"
                      : f.level === "warning"
                      ? "text-orange-600"
                      : ""
                  }
                >
                  {f.message}
                  {f.suggestion && (
                    <div className="text-sm">{f.suggestion}</div>
                  )}
                </li>
              ))}
            </ul>
            <button
              type="button"
              onClick={copyReport}
              className="rounded bg-gray-200 px-2 py-1"
            >
              {t("support.health.copyReport")}
            </button>
          </div>
        )}
      </SectionCard>

      <SectionCard title={t("support.notifications.title")}>
        <OwnerSelector owners={owners} selected={owner} onSelect={setOwner} />
        {typeof Notification === "undefined" ||
        typeof navigator === "undefined" ||
        !("serviceWorker" in navigator) ? (
          <p className="mt-2">{t("support.notifications.notSupported")}</p>
        ) : (
          <div className="mt-2 space-x-2">
            <button
              onClick={pushEnabled ? disablePush : enablePush}
              type="button"
              disabled={!owner}
              className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
            >
              {pushEnabled
                ? t("support.notifications.disable")
                : t("support.notifications.enable")}
            </button>
            {pushStatus === "denied" && (
              <p>{t("support.notifications.denied")}</p>
            )}
            {pushStatus === "error" && (
              <p>{t("support.notifications.error")}</p>
            )}
          </div>
        )}
      </SectionCard>

      <SectionCard title={t("support.config.title")}>
        {!Object.keys(config).length ? (
          <p>{t("common.loading")}</p>
        ) : (
          <form onSubmit={saveConfig} className="space-y-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <h3 className="mb-1 font-semibold">{t("support.config.tabsEnabled")}</h3>
                {TAB_KEYS.map((tab) => (
                  <label key={tab} className="mb-1 block font-medium">
                    <input
                      type="checkbox"
                      checked={tabs[tab]}
                      onChange={(e) => handleTabChange(tab, e.target.checked)}
                      className="mr-1"
                    />
                    {tab}
                  </label>
                ))}
              </div>
              <div>
                <h3 className="mb-1 font-semibold">{t("support.config.otherSwitches")}</h3>
                {Object.entries(config)
                  .filter(([k, v]) => k !== "tabs" && typeof v === "boolean")
                  .map(([key, value]) => (
                    <label key={key} className="mb-1 block font-medium">
                      <input
                        type="checkbox"
                        checked={value as boolean}
                        onChange={(e) => handleConfigChange(key, e.target.checked)}
                        className="mr-1"
                      />
                      {key}
                    </label>
                  ))}
              </div>
            </div>
            <div>
              <h3 className="mb-1 font-semibold">{t("support.config.otherParams")}</h3>
              {Object.entries(config)
                .filter(([k, v]) => k !== "tabs" && typeof v !== "boolean")
                .map(([key, value]) => (
                  <div key={key} className="mb-2">
                    {key === "theme" && typeof value === "string" ? (
                      <div>
                        <label className="mb-1 block font-medium">{key}</label>
                        {["dark", "light", "system"].map((opt) => (
                          <label key={opt} className="mr-2">
                            <input
                              type="radio"
                              name="theme"
                              value={opt}
                              checked={value === opt}
                              onChange={(e) => handleConfigChange(key, e.target.value)}
                              className="mr-1"
                            />
                            {opt}
                          </label>
                        ))}
                      </div>
                    ) : (
                      <input
                        type="text"
                        value={String(value ?? "")}
                        onChange={(e) => handleConfigChange(key, e.target.value)}
                        className="w-full rounded border px-2 py-1"
                      />
                    )}
                  </div>
                ))}
            </div>
            <div>
              <button
                type="submit"
                className="rounded bg-green-600 px-4 py-2 text-white hover:bg-green-700"
              >
                {t("support.config.save")}
              </button>
              {configStatus === "saved" && (
                <span className="ml-2 text-green-600">
                  {t("support.status.saved")}
                </span>
              )}
              {configStatus === "error" && (
                <span className="ml-2 text-red-600">
                  {t("support.status.error")}
                </span>
              )}
              {configStatus === "saving" && (
                <span className="ml-2">{t("support.status.saving")}</span>
              )}
            </div>
          </form>
        )}
      </SectionCard>

      <SectionCard title={t("support.telegramMessage")}>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          rows={4}
          className="w-full rounded border px-2 py-1"
        />
        <div className="mt-2">
          <button
            onClick={send}
            disabled={!message}
            className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
          >
            {t("support.send")}
          </button>
          {status === "sent" && (
            <span className="ml-2 text-green-600">{t("support.status.sent")}</span>
          )}
          {status === "error" && (
            <span className="ml-2 text-red-600">{t("support.status.error")}</span>
          )}
          {status === "sending" && (
            <span className="ml-2">{t("support.status.sending")}</span>
          )}
        </div>
      </SectionCard>
    </div>
  );
}

