import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getOwners, getPortfolio } from "../api";
import { PortfolioView } from "../components/PortfolioView";
import { OwnerSelector } from "../components/OwnerSelector";
import Meta from "../components/Meta";
import { useRoute } from "../RouteContext";
import { sanitizeOwners } from "../utils/owners";
import type { OwnerSummary, Portfolio as PortfolioData } from "../types";

export function Portfolio() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [data, setData] = useState<PortfolioData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [ownersLoading, setOwnersLoading] = useState(true);
  const [ownersError, setOwnersError] = useState<string | null>(null);
  const BASE_URL = import.meta.env.VITE_APP_BASE_URL || "https://app.allotmint.io";

  const { owner: ownerParam } = useParams<{ owner?: string }>();
  const ownerSlug = ownerParam?.trim() ?? "";

  let routeContext: ReturnType<typeof useRoute> | null = null;
  try {
    routeContext = useRoute();
  } catch {
    routeContext = null;
  }

  const routeOwner = routeContext?.selectedOwner ?? "";
  const setRouteOwner = routeContext?.setSelectedOwner;

  const activeOwner = useMemo(
    () => (ownerSlug ? ownerSlug : routeOwner ? routeOwner.trim() : ""),
    [ownerSlug, routeOwner],
  );

  const handleOwnerChange = useCallback(
    (nextOwner: string) => {
      const trimmed = nextOwner.trim();
      if (setRouteOwner) {
        setRouteOwner(trimmed);
      }
      navigate(trimmed ? `/portfolio/${trimmed}` : "/portfolio");
    },
    [navigate, setRouteOwner],
  );

  useEffect(() => {
    if (!setRouteOwner) return;
    if (ownerSlug && ownerSlug !== routeOwner) {
      setRouteOwner(ownerSlug);
    }
    if (!ownerSlug && routeOwner) {
      setRouteOwner("");
    }
  }, [ownerSlug, routeOwner, setRouteOwner]);

  useEffect(() => {
    let cancelled = false;
    setOwnersLoading(true);
    setOwnersError(null);
    getOwners()
      .then((list) => {
        if (cancelled) return;
        const sanitized = sanitizeOwners(Array.isArray(list) ? list : []);
        setOwners(sanitized);
      })
      .catch((err) => {
        if (cancelled) return;
        setOwners([]);
        setOwnersError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setOwnersLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (owners.length === 1 && !activeOwner) {
      handleOwnerChange(owners[0].owner);
    }
  }, [owners, activeOwner, handleOwnerChange]);

  useEffect(() => {
    if (!activeOwner) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    setData(null);
    getPortfolio(activeOwner)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch(() => setError("Failed to load portfolio"))
      .finally(() => setLoading(false));
  }, [activeOwner]);

  return (
    <>
      <Meta
        title="Portfolio"
        description="View and manage your investment portfolio"
        canonical={`${BASE_URL}/portfolio`}
        jsonLd={{
          '@context': 'https://schema.org',
          '@type': 'WebPage',
          name: 'Portfolio',
          url: `${BASE_URL}/portfolio`,
          description: 'View and manage your investment portfolio',
          image: `${BASE_URL}/vite.svg`,
        }}
      />
      <div className="p-4 md:p-8">
        <div className="mb-6">
          {ownersLoading ? (
            <p className="text-sm text-gray-400">Loading owners…</p>
          ) : owners.length > 0 ? (
            <OwnerSelector
              owners={owners}
              selected={activeOwner}
              onSelect={handleOwnerChange}
            />
          ) : ownersError ? (
            <p className="text-sm text-red-500">{ownersError}</p>
          ) : (
            <p className="text-sm text-gray-400">{t("owner.noOwners")}</p>
          )}
          {!ownersLoading && owners.length > 0 && !activeOwner && (
            <p className="mt-2 text-sm text-gray-400">{t("owner.select")}</p>
          )}
        </div>
        <PortfolioView data={data} loading={loading} error={error} />
      </div>
    </>
  );
}

export default Portfolio;
