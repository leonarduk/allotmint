import { NavLink, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

const modes = [
  "group",
  "instrument",
  "owner",
  "performance",
  "transactions",
  "screener",
  "query",
  "trading",
  "timeseries",
] as const;

type Mode = (typeof modes)[number];

export function NavigationBar() {
  const { t } = useTranslation();
  const location = useLocation();
  const current = location.pathname.split("/")[2] as Mode | undefined;

  return (
    <nav role="tablist" aria-label={t("app.viewBy") ?? "Portfolio modes"}>
      {modes.map((m) => (
        <NavLink
          key={m}
          to={`/portfolio/${m}`}
          role="tab"
          id={`tab-${m}`}
          aria-selected={current === m}
          tabIndex={current === m ? 0 : -1}
          aria-controls={`tabpanel-${m}`}
          style={{ marginRight: "1rem" }}
        >
          {t(`app.modes.${m}`)}
        </NavLink>
      ))}
    </nav>
  );
}
