import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import AppHeader from "../components/AppHeader";
import PriceTriggersPanel from "../components/PriceTriggersPanel";
import { getAlertThreshold, setAlertThreshold } from "../api";
import { usePriceRefresh } from "../PriceRefreshContext";
import { useDemoReadOnly } from "../hooks/useDemoReadOnly";
import { useAlertIdentity } from "../hooks/useAlertIdentity";

const HTTP_FORBIDDEN = 403;

export default function AlertSettings() {
  const { t } = useTranslation();
  const { lastRefresh } = usePriceRefresh();
  const { demoReadOnly, reason } = useDemoReadOnly();

  const { identity, displayOwner, resolving, forbidden, saveDisabled, setForbidden } =
    useAlertIdentity();

  const [threshold, setThreshold] = useState<number | "">("");
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">(
    "idle",
  );

  useEffect(() => {
    setForbidden(false);
    if (!identity) {
      setThreshold("");
      return;
    }
    let cancelled = false;
    getAlertThreshold(identity)
      .then((r) => {
        if (cancelled) return;
        setThreshold(r.threshold);
      })
      .catch((err) => {
        if (cancelled) return;
        setThreshold("");
        if ((err as { status?: number })?.status === HTTP_FORBIDDEN) {
          setForbidden(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [identity, setForbidden]);

  async function save() {
    if (threshold === "" || !identity || forbidden) return;
    setStatus("saving");
    try {
      await setAlertThreshold(identity, Number(threshold));
      setStatus("saved");
    } catch (err) {
      if ((err as { status?: number })?.status === HTTP_FORBIDDEN) {
        setForbidden(true);
        setStatus("idle");
      } else {
        setStatus("error");
      }
    }
  }

  return (
    <div style={{ padding: "1rem" }}>
      <AppHeader lastRefresh={lastRefresh} />
      <div style={{ maxWidth: 600 }}>
        <h1>{t("alertSettings.title")}</h1>
        <p>{t("alertSettings.description")}</p>
        <p>
          <Link to="/alerts">{t("alertSettings.viewAlertsLink")}</Link>
        </p>
        {resolving && <p>{t("alertSettings.resolving")}</p>}
        {!resolving && !identity && <p>{t("alertSettings.signInNotice")}</p>}
        {!resolving && identity && !forbidden && (
          <p>{t("alertSettings.managingFor", { owner: displayOwner })}</p>
        )}
        {!resolving && identity && forbidden && (
          <p>{t("alertSettings.forbiddenNotice", { owner: identity })}</p>
        )}
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
              disabled={saveDisabled}
            />
          </label>
          <button
            onClick={save}
            style={{ marginLeft: "0.5rem" }}
            disabled={saveDisabled || demoReadOnly}
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
        {!resolving && identity && !forbidden && (
          <PriceTriggersPanel
            identity={identity}
            disabled={demoReadOnly}
            disabledReason={reason()}
          />
        )}
        <div style={{ marginTop: "2rem" }}>
          <h2>{t("alertSettings.push.title")}</h2>
          {/* Push notifications have no implementation anywhere in this app
              (no PushManager/service-worker subscription code exists) -- this
              is not a browser capability check, so the copy says so plainly
              rather than implying an unsupported-browser state. Alerts remain
              reachable via the "View recent alerts" link above (#7207). */}
          <p>{t("alertSettings.push.notSupported")}</p>
        </div>
      </div>
    </div>
  );
}
