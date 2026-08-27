import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation } from "react-router-dom";
import AppHeader from "../components/AppHeader";
import {
  getAlertThreshold,
  getOwners,
  setAlertThreshold,
} from "../api";
import { useUser } from "../UserContext";
import { usePriceRefresh } from "../PriceRefreshContext";
import { sanitizeOwners } from "../utils/owners";
import type { OwnerSummary } from "../types";

const HTTP_FORBIDDEN = 403;

export default function AlertSettings() {
  const { t } = useTranslation();
  const { profile } = useUser();
  const { lastRefresh } = usePriceRefresh();
  const location = useLocation();

  // AlertSettings is mounted as a standalone route (see routes/registry.ts)
  // outside <RouteProvider>, so it can't call useRoute() like most other
  // pages do. It resolves the acting owner the same way the rest of the app
  // scopes requests instead of depending on an authenticated profile:
  //   1. the `?owner=` query param the nav link now carries (mirrors the
  //      owner/group scoping useRouteMode derives for in-context pages);
  //   2. the first owner from /owners, so the page works the same way
  //      PensionForecast etc. do on a direct visit with nothing selected yet
  //      -- this is what makes it usable in the local/demo deployment, where
  //      every other page already shows all owners without a signed-in
  //      profile;
  //   3. profile?.email as a last resort.
  const queryOwner = useMemo(
    () => new URLSearchParams(location.search).get("owner")?.trim() ?? "",
    [location.search],
  );
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  useEffect(() => {
    if (queryOwner) return;
    let cancelled = false;
    getOwners()
      .then((os) => {
        if (!cancelled) setOwners(sanitizeOwners(os));
      })
      .catch(() => {
        if (!cancelled) setOwners([]);
      });
    return () => {
      cancelled = true;
    };
  }, [queryOwner]);
  const owner = queryOwner || owners[0]?.owner || profile?.email || "";

  const [threshold, setThreshold] = useState<number | "">("");
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">(
    "idle",
  );
  // Set when the backend rejects this owner as an authorisation mismatch
  // (alert thresholds are scoped to a single signed-in identity, unlike
  // portfolio data). Kept distinct from `status` so the UI can explain the
  // real reason Save is unavailable instead of a generic sign-in notice.
  const [forbidden, setForbidden] = useState(false);

  useEffect(() => {
    setForbidden(false);
    if (!owner) {
      setThreshold("");
      return;
    }
    let cancelled = false;
    getAlertThreshold(owner)
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
  }, [owner]);

  async function save() {
    if (threshold === "" || !owner || forbidden) return;
    setStatus("saving");
    try {
      await setAlertThreshold(owner, Number(threshold));
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

  const saveDisabled = !owner || forbidden;

  return (
    <div style={{ padding: "1rem" }}>
      <AppHeader lastRefresh={lastRefresh} />
      <div style={{ maxWidth: 600 }}>
        <h1>{t("alertSettings.title")}</h1>
        <p>{t("alertSettings.description")}</p>
        <p>
          <Link to="/alerts">{t("alertSettings.viewAlertsLink")}</Link>
        </p>
        {!owner && <p>{t("alertSettings.signInNotice")}</p>}
        {owner && forbidden && (
          <p>{t("alertSettings.forbiddenNotice", { owner })}</p>
        )}
        <div style={{ marginTop: "1rem" }}>
          <label>
            {t("alertSettings.threshold.prefix")}{" "}
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
            />{" "}
            {t("alertSettings.threshold.suffix")}
          </label>
          <button
            onClick={save}
            style={{ marginLeft: "0.5rem" }}
            disabled={saveDisabled}
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
