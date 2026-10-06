import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  API_BASE,
  getConfig,
  getMcpTools,
  getOwners,
  type McpToolSwitch,
  updateConfig,
  checkPortfolioHealth,
  getLogs,
  type Finding,
  refreshPrices,
  getRefreshPricesProgress,
  clearGroupInstrumentCache,
} from "../api";
import { clearFetchCache } from "../utils/fetchCache";
import { MCP_TOOL_SETUP_DOCS_URL } from "../utils/docsLinks";
import { useConfig } from "../ConfigContext";
import { useAuth } from "../AuthContext";
import { useUser } from "../UserContext";
import { OwnerSelector } from "../components/OwnerSelector";
import SectionCard from "../components/SectionCard";
import AppUpdateSection from "../components/AppUpdateSection";
import type { OwnerSummary } from "../types";
import { orderedTabPlugins, type TabPluginId } from "../tabPlugins";
import { usePriceRefresh } from "../PriceRefreshContext";
import { sanitizeOwners } from "../utils/owners";

const TAB_KEYS = orderedTabPlugins.map((p) => p.id) as TabPluginId[];
const EMPTY_TABS = Object.fromEntries(TAB_KEYS.map((k) => [k, false])) as Record<
  TabPluginId,
  boolean
>;

const UI_KEYS = new Set(["theme", "relative_view_enabled"]);
// Rendered by the MCP tools section, not the generic parameter list.
const MCP_TOOLS_KEY = "mcp_tools";

// DOM id for an MCP tool's "not configured" note: derived from the tool name
// (stable across reorders), with characters not safe in an id replaced.
function mcpToolStatusId(toolName: string): string {
  return `mcp-tool-status-${toolName.replace(/[^A-Za-z0-9_-]/g, "-")}`;
}

type ConfigValue = string | boolean | Record<string, unknown>;
type ConfigState = Record<string, ConfigValue>;

function toConfigState(cfg: Record<string, unknown>): ConfigState {
  const entries: ConfigState = {};
  Object.entries(cfg).forEach(([k, v]) => {
    if (v && typeof v === "object" && !Array.isArray(v)) {
      entries[k] = v as Record<string, unknown>;
    } else {
      entries[k] = typeof v === "boolean" ? v : v == null ? "" : String(v);
    }
  });
  return entries;
}

function toTabState(cfg: Record<string, unknown>): Record<TabPluginId, boolean> {
  const tabConfig =
    cfg.tabs && typeof cfg.tabs === "object" ? (cfg.tabs as Record<string, unknown>) : {};
  return TAB_KEYS.reduce(
    (acc, key) => ({ ...acc, [key]: Boolean(tabConfig[key]) }),
    { ...EMPTY_TABS },
  );
}

export default function Support() {
  const { t } = useTranslation();
  const { refreshConfig } = useConfig();
  const { setUser } = useAuth();
  const { setProfile } = useUser();
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [config, setConfig] = useState<ConfigState>({});
  const [tabs, setTabs] = useState<Record<TabPluginId, boolean>>(EMPTY_TABS);
  // What was last loaded from / saved to the backend. saveConfig sends only
  // fields that differ from this, so an untouched form never writes the
  // resolved config (absolute paths, "[object Object]" for object values)
  // back into config.yaml (#7896).
  const [savedConfig, setSavedConfig] = useState<ConfigState>({});
  const [savedTabs, setSavedTabs] = useState<Record<TabPluginId, boolean>>(EMPTY_TABS);
  const [configStatus, setConfigStatus] = useState<string | null>(null);
  const [mcpTools, setMcpTools] = useState<McpToolSwitch[]>([]);
  const [savedMcpTools, setSavedMcpTools] = useState<Record<string, boolean>>({});
  const [mcpError, setMcpError] = useState<string | null>(null);
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [owner, setOwner] = useState("");
  const [health, setHealth] = useState<Finding[]>([]);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [healthRunning, setHealthRunning] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [refreshProgress, setRefreshProgress] = useState<{
    completed: number;
    total: number;
    currentTicker: string | null;
  } | null>(null);
  const refreshProgressTimer = useRef<number | null>(null);
  // Guards against a poll response landing after the refresh itself has
  // already finished (interval cleared, but the in-flight fetch it kicked
  // off hasn't resolved yet) — without this, that straggler could briefly
  // repaint stale progress after the button has already re-enabled.
  const refreshActive = useRef(false);
  const [logs, setLogs] = useState("");
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState<string | null>(null);
  const [localLogin, setLocalLogin] = useState("");
  const [localLoginStatus, setLocalLoginStatus] = useState<
    "idle" | "saving" | "saved" | "error"
  >("idle");
  const { lastRefresh, setLastRefresh } = usePriceRefresh();
  const localLoginResetTimer = useRef<number | null>(null);

  const envEntries = Object.entries(import.meta.env).sort();
  const online = typeof navigator !== "undefined" ? navigator.onLine : true;

  const ownerLoginMap = useMemo(() => {
    const map = new Map<
      string,
      { owner: OwnerSummary; login: string; email?: string }
    >();
    owners.forEach((entry) => {
      if (!entry?.owner) return;
      const trimmedEmail =
        typeof entry.email === "string" ? entry.email.trim() : "";
      const login = trimmedEmail || entry.owner;
      map.set(login, {
        owner: entry,
        login,
        email: trimmedEmail || undefined,
      });
    });
    return map;
  }, [owners]);

  const localLoginOptions = useMemo(
    () =>
      Array.from(ownerLoginMap.values())
        .map(({ owner: entry, login, email }) => {
          const displayName = entry.full_name?.trim() || entry.owner;
          return {
            value: login,
            label: email
              ? `${displayName} (${email})`
              : `${displayName} (${entry.owner})`,
            name: displayName,
          };
        })
        .sort((a, b) => a.label.localeCompare(b.label)),
    [ownerLoginMap],
  );

  const scheduleLocalLoginStatusReset = useCallback(() => {
    if (localLoginResetTimer.current !== null) {
      window.clearTimeout(localLoginResetTimer.current);
    }
    localLoginResetTimer.current = window.setTimeout(() => {
      setLocalLoginStatus("idle");
      localLoginResetTimer.current = null;
    }, 2000);
  }, [localLoginResetTimer]);

  const handleLocalLoginChange = useCallback(
    async (value: string) => {
      const trimmed = value.trim();
      setLocalLogin(trimmed);
      setLocalLoginStatus("saving");
      const payload =
        trimmed.length > 0
          ? { auth: { local_login_email: trimmed } }
          : { auth: { local_login_email: null } };
      try {
        await updateConfig(payload);
        setConfig((prev) => ({ ...prev, local_login_email: trimmed }));
        setSavedConfig((prev) => ({ ...prev, local_login_email: trimmed }));
        await refreshConfig();
        if (trimmed) {
          const entry = ownerLoginMap.get(trimmed);
          const displayName =
            entry?.owner.full_name?.trim() || entry?.owner.owner || trimmed;
          const resolvedEmail =
            entry?.email || entry?.owner.owner || trimmed;
          setUser({ email: resolvedEmail, name: displayName });
          setProfile({ email: resolvedEmail, name: displayName });
        } else {
          setUser(null);
          setProfile(undefined);
        }
        setLocalLoginStatus("saved");
      } catch (err) {
        console.error("Failed to update local login override", err);
        setLocalLoginStatus("error");
      } finally {
        scheduleLocalLoginStatusReset();
      }
    },
    [ownerLoginMap, refreshConfig, scheduleLocalLoginStatusReset, setProfile, setUser],
  );

  useEffect(() => {
    getOwners()
      .then((list) => {
        const sanitized = sanitizeOwners(list);
        setOwners(sanitized);
        setOwner(sanitized[0]?.owner ?? "");
      })
      .catch(() => setOwners([]));
  }, []);

  useEffect(() => {
    getConfig()
      .then((cfg) => {
        const entries = toConfigState(cfg as Record<string, unknown>);
        setConfig(entries);
        setSavedConfig(entries);
        const rawLocalLogin = (cfg as Record<string, unknown>)[
          "local_login_email"
        ];
        const configuredLocalLogin =
          typeof rawLocalLogin === "string" ? rawLocalLogin : "";
        setLocalLogin(configuredLocalLogin.trim());
        const loadedTabs = toTabState(cfg as Record<string, unknown>);
        setTabs(loadedTabs);
        setSavedTabs(loadedTabs);
      })
      .catch(() => {
        /* ignore */
      });
  }, []);

  const loadMcpTools = useCallback(() => {
    getMcpTools()
      .then((res) => {
        setMcpTools(res.tools);
        setSavedMcpTools(Object.fromEntries(res.tools.map((tool) => [tool.name, tool.enabled])));
        setMcpError(res.mcp_error);
      })
      .catch(() => setMcpError(t("support.config.mcpToolsUnavailable")));
  }, [t]);

  useEffect(() => {
    loadMcpTools();
  }, [loadMcpTools]);

  useEffect(() => {
    return () => {
      if (localLoginResetTimer.current !== null) {
        window.clearTimeout(localLoginResetTimer.current);
        localLoginResetTimer.current = null;
      }
      if (refreshProgressTimer.current !== null) {
        window.clearInterval(refreshProgressTimer.current);
        refreshProgressTimer.current = null;
      }
      refreshActive.current = false;
    };
  }, []);

  function handleConfigChange(key: string, value: string | boolean) {
    setConfig((prev) => ({ ...prev, [key]: value }));
  }

  function handleTabChange(key: TabPluginId, value: boolean) {
    setTabs((prev) => ({ ...prev, [key]: value }));
  }

  function handleMcpToolChange(name: string, enabled: boolean) {
    setMcpTools((prev) => prev.map((tool) => (tool.name === name ? { ...tool, enabled } : tool)));
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
    setRefreshProgress(null);
    refreshActive.current = true;

    // Poll for incremental progress while the refresh runs, so the user sees
    // which ticker is being fetched rather than a static "Refreshing..."
    // label for the whole (potentially long) job. A poll failure is not
    // fatal to the refresh itself, so it's swallowed here — the button just
    // falls back to the plain label for that tick.
    refreshProgressTimer.current = window.setInterval(() => {
      getRefreshPricesProgress()
        .then((p) => {
          if (refreshActive.current && p.running) {
            setRefreshProgress({
              completed: p.completed,
              total: p.total,
              currentTicker: p.current_ticker,
            });
          }
        })
        .catch(() => {
          /* ignore — the refresh itself is still tracked below */
        });
    }, 400);

    try {
      const resp = await refreshPrices();
      // Every cached portfolio/valuation response was computed against the old
      // prices, so drop the lot rather than let the overview render pre-refresh
      // numbers for up to its TTL after the user explicitly asked for new ones.
      clearFetchCache();
      clearGroupInstrumentCache();
      setLastRefresh(resp.timestamp ?? new Date().toISOString());
    } catch (e) {
      setRefreshError(e instanceof Error ? e.message : String(e));
    } finally {
      refreshActive.current = false;
      if (refreshProgressTimer.current !== null) {
        window.clearInterval(refreshProgressTimer.current);
        refreshProgressTimer.current = null;
      }
      setRefreshProgress(null);
      setRefreshing(false);
    }
  }

  const loadLogs = useCallback(async () => {
    setLogsLoading(true);
    setLogsError(null);
    try {
      const text = await getLogs();
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
      if (k === "tabs" || k === MCP_TOOLS_KEY) continue; // rebuilt from toggle state
      if (v === savedConfig[k]) continue; // unchanged -- see savedConfig
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
    if (TAB_KEYS.some((key) => tabs[key] !== savedTabs[key])) {
      ui.tabs = { ...tabs };
    }
    if (Object.keys(ui).length) {
      payload.ui = ui;
    }
    if (mcpTools.some((tool) => tool.enabled !== savedMcpTools[tool.name])) {
      // Sent under the ``mcp`` section: config.yaml flattens one level, so a
      // top-level mcp_tools map would be read back as separate keys.
      payload.mcp = {
        mcp_tools: Object.fromEntries(mcpTools.map((tool) => [tool.name, tool.enabled])),
      };
    }
    try {
      await updateConfig(payload);
      await refreshConfig();
      const fresh = await getConfig();
      const entries = toConfigState(fresh as Record<string, unknown>);
      setConfig(entries);
      setSavedConfig(entries);
      const freshTabs = toTabState(fresh as Record<string, unknown>);
      setTabs(freshTabs);
      setSavedTabs(freshTabs);
      loadMcpTools();
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

      <div id="local-login-override">
        <SectionCard
          title={t("support.localLogin.title", "Local login override")}
          defaultOpen={window.location.hash === "#local-login-override"}
        >
        <p className="mb-2 text-sm text-gray-600">
          {t(
            "support.localLogin.description",
            "Select which user email should be assumed when authentication is disabled.",
          )}
        </p>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <label
            htmlFor="support-local-login-select"
            className="text-sm font-medium"
          >
            {t("support.localLogin.label", "Active user")}
          </label>
          <select
            id="support-local-login-select"
            value={localLogin}
            onChange={(event) => handleLocalLoginChange(event.target.value)}
            disabled={
              localLoginStatus === "saving" || localLoginOptions.length === 0
            }
            className="w-full rounded border border-gray-300 p-2 text-sm sm:w-auto"
          >
            <option value="">
              {t("support.localLogin.none", "No override configured")}
            </option>
            {localLoginOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        {localLoginOptions.length === 0 && (
          <p className="mt-2 text-sm text-gray-500">
            {t(
              "support.localLogin.noOwners",
              "No owners available to assume.",
            )}
          </p>
        )}
        {localLoginStatus !== "idle" && (
          <p
            className={`mt-2 text-sm ${
              localLoginStatus === "error" ? "text-red-600" : "text-gray-600"
            }`}
          >
            {localLoginStatus === "saving"
              ? t("support.status.saving")
              : localLoginStatus === "saved"
              ? t("support.status.saved")
              : t("support.status.error")}
          </p>
        )}
        </SectionCard>
      </div>

      <AppUpdateSection />

      <SectionCard title={t("support.dataExplorer.title", "Data Explorer")}>
        <p className="mb-2 text-sm text-gray-600">
          {t(
            "support.dataExplorer.description",
            "Browse the backend data area (local files, or S3 in the AWS deployment) to inspect account, price, and timeseries data.",
          )}
        </p>
        <Link
          to="/data-explorer"
          className="inline-block rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
        >
          {t("support.dataExplorer.link", "Open Data Explorer")}
        </Link>
      </SectionCard>

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
                      <a href={`${base}/api-console`}>API Console</a>
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
          {refreshing
            ? refreshProgress && refreshProgress.total > 0
              ? t("app.refreshingProgress", {
                  completed: refreshProgress.completed,
                  total: refreshProgress.total,
                })
              : t("app.refreshing")
            : t("app.refreshPrices")}
        </button>
        {refreshing && refreshProgress && refreshProgress.total > 0 && (
          <div className="mt-2" role="status">
            <progress
              className="w-full"
              value={refreshProgress.completed}
              max={refreshProgress.total}
            />
            {refreshProgress.currentTicker && (
              <div className="text-sm text-gray-600">
                {t("app.refreshingTicker", { ticker: refreshProgress.currentTicker })}
              </div>
            )}
          </div>
        )}
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
        <p className="mt-2">{t("support.notifications.notSupported")}</p>
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
                  .filter(([k, v]) => k !== "tabs" && k !== MCP_TOOLS_KEY && typeof v === "boolean")
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
              <h3 className="mb-1 font-semibold">{t("support.config.mcpTools")}</h3>
              <p className="mb-1 text-sm opacity-80">{t("support.config.mcpToolsHint")}</p>
              {mcpError && <p className="mb-1 text-sm text-amber-600">{mcpError}</p>}
              <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
                {mcpTools.map((tool) => (
                  <div key={tool.name} className="mb-1">
                    <label className="block font-medium" title={tool.description}>
                      <input
                        type="checkbox"
                        checked={tool.enabled}
                        onChange={(e) => handleMcpToolChange(tool.name, e.target.checked)}
                        aria-describedby={tool.not_configured ? mcpToolStatusId(tool.name) : undefined}
                        className="mr-1"
                      />
                      {tool.name}
                    </label>
                    {tool.not_configured && (
                      <p id={mcpToolStatusId(tool.name)} className="ml-5 text-xs text-amber-600">
                        {t("support.config.mcpToolNotConfigured")}: {tool.not_configured}{" "}
                        <a
                          href={MCP_TOOL_SETUP_DOCS_URL}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="underline"
                        >
                          {t("support.config.mcpToolSetupLink")}
                        </a>
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h3 className="mb-1 font-semibold">{t("support.config.otherParams")}</h3>
              {Object.entries(config)
                .filter(([k, v]) => k !== "tabs" && k !== MCP_TOOLS_KEY && typeof v !== "boolean")
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
