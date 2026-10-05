import { useEffect, useMemo, useState } from "react";
import { getConfig, getOwners } from "../api";
import { useUser } from "../UserContext";
import {
  createOwnerDisplayLookup,
  findOwnerForUser,
  getOwnerDisplayName,
  sanitizeOwners,
} from "../utils/owners";
import type { OwnerSummary } from "../types";

/**
 * The subset of GET /config this hook needs. `disable_auth` and
 * `local_login_email` are part of the typed contract already;
 * `demo_identity` is a real field on the backend response (see
 * backend/routes/config.py -- it isn't in the SPA's secret-redaction list)
 * but isn't declared on configContractSchema, so it survives the schema's
 * `.passthrough()` at runtime without being typed. Cast for it explicitly
 * rather than widening the shared contract for one caller.
 */
export interface AlertIdentityConfig {
  disable_auth: boolean;
  local_login_email: string | null;
  demo_identity?: string;
}

export interface UseAlertIdentityResult {
  /** Resolved identity sent to the API (never a portfolio owner slug). */
  identity: string;
  /** Display-only owner name for the resolved identity, if any. */
  displayOwner: string;
  /** True until the initial config/owners fetches have settled. */
  resolving: boolean;
  /** True when the backend rejected this identity as an authorisation mismatch. */
  forbidden: boolean;
  /** True when Save must be disabled (resolving, no identity, or forbidden). */
  saveDisabled: boolean;
  /** Mark the identity as forbidden (e.g. after a 403 from a save call). */
  setForbidden: (value: boolean) => void;
}

/**
 * Resolves the identity used for alert-threshold API calls.
 *
 * /alert-thresholds/{user} (backend/routes/alert_settings.py) is scoped to a
 * single resolved IDENTITY, not to whichever owner's portfolio happens to be
 * selected in the UI: an authenticated caller's identity is their own email;
 * otherwise (auth disabled, as in the local/demo deployment) the backend
 * falls back to `local_login_email` if configured, else the shared
 * `demo_identity` -- see backend/auth.py
 * `_resolve_identity_when_auth_disabled` and backend/config.py
 * `demo_identity()`. A portfolio owner slug (e.g. "alice") is never a valid
 * identity: /owners intentionally excludes "demo" from its list (see
 * sanitizeOwners), so sending an owner slug here 403s unconditionally in this
 * deployment's config (disable_auth=true, demo_identity="demo").
 * `identity` (sent to the API) and `displayOwner` (shown on screen, for
 * context) are therefore resolved separately (#7225 review).
 */
export function useAlertIdentity(): UseAlertIdentityResult {
  const { profile } = useUser();

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

  // Resolving is true until both fetches above have settled, so consumers
  // don't flash the sign-in notice on first paint before they know whether
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

  const [forbidden, setForbidden] = useState(false);

  const saveDisabled = resolving || !identity || forbidden;

  return {
    identity,
    displayOwner,
    resolving,
    forbidden,
    saveDisabled,
    setForbidden,
  };
}
