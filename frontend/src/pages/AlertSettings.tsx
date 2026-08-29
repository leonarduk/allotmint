import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import AppHeader from "../components/AppHeader";
import {
  getAlertThreshold,
  getConfig,
  getOwners,
  setAlertThreshold,
} from "../api";
import { useUser } from "../UserContext";
import { usePriceRefresh } from "../PriceRefreshContext";
import {
  createOwnerDisplayLookup,
  findOwnerForUser,
  getOwnerDisplayName,
  sanitizeOwners,
} from "../utils/owners";
import type { OwnerSummary } from "../types";

const HTTP_FORBIDDEN = 403;

/**
 * The subset of GET /config this page needs. `disable_auth` and
 * `local_login_email` are part of the typed contract already;
 * `demo_identity` is a real field on the backend response (see
 * backend/routes/config.py -- it isn't in the SPA's secret-redaction list)
 * but isn't declared on configContractSchema, so it survives the schema's
 * `.passthrough()` at runtime without being typed. Cast for it explicitly
 * rather than widening the shared contract for one caller.
 */
interface AlertIdentityConfig {
  disable_auth: boolean;
  local_login_email: string | null;
  demo_identity?: string;
}

export default function AlertSettings() {
  const { t } = useTranslation();
  const { profile } = useUser();
  const { lastRefresh } = usePriceRefresh();

  // /alert-thresholds/{user} (backend/routes/alert_settings.py) is scoped to
  // a single resolved IDENTITY, not to whichever owner's portfolio happens
  // to be selected in the UI: an authenticated caller's identity is their
  // own email; otherwise (auth disabled, as in the local/demo deployment)
  // the backend falls back to `local_login_email` if configured, else the
  // shared `demo_identity` -- see backend/auth.py
  // `_resolve_identity_when_auth_disabled` and backend/config.py
  // `demo_identity()`. A portfolio owner slug (e.g. "alice") is never a
  // valid identity: /owners intentionally excludes "demo" from its list
  // (see sanitizeOwners), so sending an owner slug here 403s unconditionally
  // in this deployment's config (disable_auth=true, demo_identity="demo").
  // `identity` (sent to the API) and `displayOwner` (shown on screen, for
  // context) are therefore resolved separately (#7225 review).
  const [configLoaded, setConfigLoaded] = useState(false);
  const [identityConfig, setIdentityConfig] =
    useState<AlertIdentityConfig | null>(null);
  useEffect(() => {
    let cancelled = false;
    getConfig()
      .then((cfg) => {
        if (cancelled) return;
        setIdentityConfig(cfg as unknown as AlertIdentityConfig);
        setConfigLoaded(true);
      })
      .catch(() => {
        if (cancelled) return;
        setIdentityConfig(null);
        setConfigLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const [ownersLoaded, setOwnersLoaded] = useState(false);
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  useEffect(() => {
    let cancelled = false;
    getOwners()
      .then((os) => {
        if (cancelled) return;
        setOwners(sanitizeOwners(os));
        setOwnersLoaded(true);
      })
      .catch(() => {
        if (cancelled) return;
        setOwners([]);
        setOwnersLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Resolving is true until both fetches above have settled, so the page
  // doesn't flash the sign-in notice on first paint before it knows whether
  // an identity is actually available (#7225 review).
  const resolving = !configLoaded || !ownersLoaded;

  const identity = useMemo(() => {
    if (profile?.email) return profile.email;
    if (identityConfig?.disable_auth) {
      return identityConfig.local_login_email || identityConfig.demo_identity || "";
    }
    return "";
  }, [profile?.email, identityConfig]);

  // Display-only: which owner's portfolio this identity corresponds to, if
  // any, so the page can say whose alerts are being edited (never sent to
  // the API -- see `identity` above). Matched strictly by the resolved
  // identity's email -- NOT by the `?owner=` scope hint some pages append to
  // the nav link, which names whichever owner's portfolio the user was
  // *looking at*, not who the alert threshold will actually be saved for.
  // Falling back to that hint here would show one person's name while
  // silently writing to a different (usually shared/demo) identity's
  // threshold (#7225 review round 3).
  const displayOwner = useMemo(() => {
    if (!identity) return "";
    const matched = findOwnerForUser(owners, { email: identity });
    if (!matched) return identity;
    return getOwnerDisplayName(createOwnerDisplayLookup(owners), matched.owner, identity);
  }, [identity, owners]);

  const [threshold, setThreshold] = useState<number | "">("");
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">(
    "idle",
  );
  // Set when the backend rejects this identity as an authorisation mismatch.
  // Kept distinct from `status` so the UI can explain the real reason Save
  // is unavailable instead of a generic sign-in notice.
  const [forbidden, setForbidden] = useState(false);

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
  }, [identity]);

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

  const saveDisabled = resolving || !identity || forbidden;

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
