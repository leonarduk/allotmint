import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useConfig } from "../ConfigContext";
import { type Mode, MODES } from "../modes";

interface MenuProps {
  selectedOwner?: string;
  selectedGroup?: string;
}

export default function Menu({
  selectedOwner = "",
  selectedGroup = "",
}: MenuProps) {
  const location = useLocation();
  const { t } = useTranslation();
  const { tabs, disabledTabs } = useConfig();

  const params = new URLSearchParams(location.search);
  const path = location.pathname.split("/").filter(Boolean);

  const mode: Mode =
    path[0] === "member"
      ? "owner"
      : path[0] === "instrument"
      ? "instrument"
      : path[0] === "transactions"
      ? "transactions"
      : path[0] === "performance"
      ? "performance"
      : path[0] === "screener"
      ? "screener"
      : path[0] === "timeseries"
      ? "timeseries"
      : path[0] === "watchlist"
      ? "watchlist"
      : path[0] === "movers"
      ? "movers"
      : path[0] === "dataadmin"
      ? "dataadmin"
      : path[0] === "support"
      ? "support"
      : path[0] === "settings"
      ? "settings"
      : path[0] === "scenario"
      ? "scenario"
      : "group";

  function pathFor(m: Mode) {
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
      case "scenario":
        return "/scenario";
      case "settings":
        return "/settings";
      default:
        return `/${m}`;
    }
  }

  return (
    <nav style={{ margin: "1rem 0" }}>
      {MODES.filter((m) => tabs[m] === true && !disabledTabs?.includes(m)).map(
        (m) => (
          <Link
            key={m}
            to={pathFor(m)}
            style={{
              marginRight: "1rem",
              fontWeight: mode === m ? "bold" : undefined,
            }}
          >
            {t(`app.modes.${m}`)}
          </Link>
        ),
      )}
    </nav>
  );
}
