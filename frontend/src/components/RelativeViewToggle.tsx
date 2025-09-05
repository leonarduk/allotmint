import { useTranslation } from "react-i18next";
import { useConfig } from "../ConfigContext";

export function RelativeViewToggle() {
  const { t } = useTranslation();
  const { relativeViewEnabled, setRelativeViewEnabled } = useConfig();

  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
      <input
        type="checkbox"
        checked={relativeViewEnabled}
        onChange={(e) => setRelativeViewEnabled(e.target.checked)}
      />
      {t("app.relativeView")}
    </label>
  );
}
