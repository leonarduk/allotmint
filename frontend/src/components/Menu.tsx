import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useConfig } from "../ConfigContext";
import type { TabPluginId } from "../tabPlugins";
import { orderedTabPlugins } from "../tabPlugins";

interface MenuProps {
  selectedOwner?: string;
  selectedGroup?: string;
  onLogout?: () => void;
  style?: React.CSSProperties;
}

export default function Menu({
  selectedOwner = "",
  selectedGroup = "",
  onLogout,
  style,
}: MenuProps) {
  const location = useLocation();
  const { t } = useTranslation();
  const { tabs, disabledTabs } = useConfig();
  const path = location.pathname.split("/").filter(Boolean);

  const mode: TabPluginId =
    path[0] === "member"
      ? "owner"
      : path[0] === "instrument"
      ? "instrument"
      : path[0] === "transactions"
      ? "transactions"
      : path[0] === "trading"
      ? "trading"
      : path[0] === "performance"
      ? "performance"
      : path[0] === "screener"
      ? "screener"
      : path[0] === "timeseries"
      ? "timeseries"
      : path[0] === "watchlist"
      ? "watchlist"
      : path[0] === "allocation"
      ? "allocation"
      : path[0] === "movers"
      ? "movers"
      : path[0] === "instrumentadmin"
      ? "instrumentadmin"
      : path[0] === "dataadmin"
      ? "dataadmin"
      : path[0] === "profile"
      ? "profile"
      : path[0] === "virtual"
      ? "virtual"
      : path[0] === "reports"
      ? "reports"
      : path[0] === "support"
      ? "support"
      : path[0] === "settings"
      ? "settings"
      : path[0] === "profile"
      ? "settings"
      : path[0] === "scenario"
      ? "scenario"
      : path[0] === "logs"
      ? "logs"
      : path.length === 0
      ? "group"
      : "movers";

  function pathFor(m: TabPluginId) {
    switch (m) {
      case "group":
        return selectedGroup ? `/?group=${selectedGroup}` : "/";
      case "instrument":
        return selectedGroup ? `/instrument/${selectedGroup}` : "/instrument";
      case "owner":
        return selectedOwner ? `/member/${selectedOwner}` : "/member";
      case "performance":
        return selectedOwner
          ? `/performance/${selectedOwner}`
          : "/performance";
      case "movers":
        return "/movers";
      case "trading":
        return "/trading";
      case "scenario":
        return "/scenario";
      case "reports":
        return "/reports";
      case "settings":
        return "/settings";
      case "logs":
        return "/logs";
      case "allocation":
        return "/allocation";
      case "instrumentadmin":
        return "/instrumentadmin";
      case "profile":
        return "/profile";
      default:
        return `/${m}`;
    }
  }

  return (
    <nav style={{ margin: "1rem 0", ...(style ?? {}) }}>
      {orderedTabPlugins
        .slice()
        .sort((a, b) => a.priority - b.priority)
        .filter((p) => tabs[p.id] !== false && !disabledTabs?.includes(p.id))
        .map((p) => (
          <Link
            key={p.id}
            to={pathFor(p.id)}
            style={{
              marginRight: "1rem",
              fontWeight: mode === p.id ? "bold" : undefined,
            }}
          >
            {t(`app.modes.${p.id}`)}
          </Link>
        ))}
      {onLogout && (
        <button
          type="button"
          onClick={onLogout}
          style={{
            marginRight: "1rem",
            background: "none",
            border: "none",
            padding: 0,
            font: "inherit",
            cursor: "pointer",
          }}
        >
          {t("app.logout", "Logout")}
        </button>
      )}
    </nav>
  );
}
