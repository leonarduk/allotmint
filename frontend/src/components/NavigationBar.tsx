import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";

export function NavigationBar() {
  const { t } = useTranslation();
  const linkStyle = ({ isActive }: { isActive: boolean }) => ({
    marginRight: "1rem",
    textDecoration: "none",
    fontWeight: isActive ? "bold" : undefined,
  });

  return (
    <nav style={{ marginBottom: "1rem" }}>
      <NavLink to="/group" style={linkStyle}>
        {t("app.modes.group")}
      </NavLink>
      <NavLink to="/instrument" style={linkStyle}>
        {t("app.modes.instrument")}
      </NavLink>
      <NavLink to="/owner" style={linkStyle}>
        {t("app.modes.owner")}
      </NavLink>
      <NavLink to="/performance" style={linkStyle}>
        {t("app.modes.performance")}
      </NavLink>
      <NavLink to="/transactions" style={linkStyle}>
        {t("app.modes.transactions")}
      </NavLink>
      <NavLink to="/screener" style={linkStyle}>
        {t("app.modes.screener")}
      </NavLink>
      <NavLink to="/query" style={linkStyle}>
        {t("app.modes.query")}
      </NavLink>
      <NavLink to="/trading" style={linkStyle}>
        {t("app.modes.trading")}
      </NavLink>
      <NavLink to="/timeseries" style={linkStyle}>
        {t("app.modes.timeseries")}
      </NavLink>
      <NavLink to="/virtual" style={linkStyle}>
        {t("app.modes.virtual")}
      </NavLink>
      <NavLink to="/support" style={linkStyle}>
        {t("app.modes.support")}
      </NavLink>
    </nav>
  );
}

export default NavigationBar;
