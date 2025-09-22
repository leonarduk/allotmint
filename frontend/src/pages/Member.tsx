import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { getOwners, getPortfolio } from "../api";
import SummaryBar from "../components/SummaryBar";
import { PortfolioView } from "../components/PortfolioView";
import { useRoute } from "../RouteContext";
import useFetchWithRetry from "../hooks/useFetchWithRetry";
import type { OwnerSummary, Portfolio } from "../types";

export function Member() {
  const { owner: ownerParam } = useParams<{ owner?: string }>();
  const navigate = useNavigate();

  let routeSelectedOwner = ownerParam ?? "";
  let routeContextOwner: string | undefined;
  let routeSetSelectedOwner: ((owner: string) => void) | undefined;
  try {
    const route = useRoute();
    routeContextOwner = route.selectedOwner;
    routeSetSelectedOwner = route.setSelectedOwner;
    if (route.selectedOwner) {
      routeSelectedOwner = route.selectedOwner;
    } else if (ownerParam) {
      routeSelectedOwner = ownerParam;
    }
  } catch {
    // Route context is optional when this page is rendered in isolation.
  }

  const activeOwner = routeSelectedOwner;

  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryNonce, setRetryNonce] = useState(0);

  const ownersReq = useFetchWithRetry<OwnerSummary[]>(
    () => getOwners(),
    500,
    5,
    [retryNonce],
  );

  useEffect(() => {
    if (!routeSetSelectedOwner) return;
    if (ownerParam && ownerParam !== routeContextOwner) {
      routeSetSelectedOwner(ownerParam);
    } else if (!ownerParam && routeContextOwner) {
      routeSetSelectedOwner("");
    }
  }, [ownerParam, routeContextOwner, routeSetSelectedOwner]);

  useEffect(() => {
    if (!activeOwner) {
      setPortfolio(null);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;

    setLoading(true);
    setError(null);
    setPortfolio(null);

    getPortfolio(activeOwner)
      .then((p) => {
        if (!cancelled) {
          setPortfolio(p);
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [activeOwner, retryNonce]);

  const handleOwnerChange = useCallback(
    (owner: string) => {
      routeSetSelectedOwner?.(owner);
      navigate(owner ? `/member/${owner}` : "/member");
    },
    [navigate, routeSetSelectedOwner],
  );

  const handleRefresh = useCallback(() => {
    setRetryNonce((n) => n + 1);
  }, []);

  return (
    <div className="p-4 md:p-8 space-y-4">
      <SummaryBar
        owners={ownersReq.data ?? []}
        owner={activeOwner}
        onOwnerChange={handleOwnerChange}
        onRefresh={handleRefresh}
      />
      <PortfolioView data={portfolio} loading={loading} error={error} />
    </div>
  );
}

export default Member;
