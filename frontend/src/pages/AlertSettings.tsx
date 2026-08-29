import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import AppHeader from "../components/AppHeader";
import {
  getAlertThreshold,
  setAlertThreshold,
} from "../api";
import { useUser } from "../UserContext";
import { usePriceRefresh } from "../PriceRefreshContext";
import { useDemoReadOnly } from "../hooks/useDemoReadOnly";

export default function AlertSettings() {
  const { t } = useTranslation();
  const { profile } = useUser();
  const { lastRefresh } = usePriceRefresh();
  const { demoReadOnly, reason } = useDemoReadOnly();
  // Owner is determined from the authenticated user's profile
  const owner = profile?.email;
  const [threshold, setThreshold] = useState<number | "">("");
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">(
    "idle",
  );
  useEffect(() => {
    if (!owner) {
      setThreshold("");
      return;
    }
    getAlertThreshold(owner)
      .then((r) => setThreshold(r.threshold))
      .catch(() => setThreshold(""));
  }, [owner]);

  async function save() {
    if (threshold === "" || !owner) return;
    setStatus("saving");
    try {
      await setAlertThreshold(owner, Number(threshold));
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  return (
    <div style={{ padding: "1rem" }}>
      <AppHeader lastRefresh={lastRefresh} />
      <div style={{ maxWidth: 600 }}>
        <h1>{t("alertSettings.title")}</h1>
        <p>{t("alertSettings.description")}</p>
        {!owner && <p>{t("alertSettings.signInNotice")}</p>}
        <div style={{ marginTop: "1rem" }}>
          <label>
            {t("alertSettings.threshold")}{" "}
            <input
              type="number"
              value={threshold}
              onChange={(e) =>
                setThreshold(
                  e.target.value === "" ? "" : Number(e.target.value),
                )
              }
              style={{ width: "4rem" }}
            />
          </label>
          <button
            onClick={save}
            style={{ marginLeft: "0.5rem" }}
            disabled={!owner || demoReadOnly}
            title={reason()}
          >
            {t("alertSettings.save")}
          </button>
          {status === "saved" && (
            <span style={{ marginLeft: "0.5rem" }}>
              {t("alertSettings.status.saved")}
            </span>
          )}
          {status === "error" && (
            <span style={{ marginLeft: "0.5rem" }}>
              {t("alertSettings.status.error")}
            </span>
          )}
        </div>
        <div style={{ marginTop: "2rem" }}>
          <h2>{t("alertSettings.push.title")}</h2>
          <p>{t("alertSettings.push.notSupported")}</p>
        </div>
      </div>
    </div>
  );
}
