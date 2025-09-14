import { useEffect, useState } from "react";
import { getOwners, getPortfolio } from "../api";
import SummaryBar from "../components/SummaryBar";
import { PortfolioView } from "../components/PortfolioView";
import { useRoute } from "../RouteContext";
import useFetchWithRetry from "../hooks/useFetchWithRetry";
import type { OwnerSummary, Portfolio } from "../types";

export function Member() {
  const { selectedOwner, setSelectedOwner } = useRoute();
  const [retryNonce, setRetryNonce] = useState(0);

  const ownersReq = useFetchWithRetry<OwnerSummary[]>(getOwners, 500, 5, [retryNonce]);

  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedOwner) {
      setPortfolio(null);
      return;
    }
    setLoading(true);
    setError(null);
    getPortfolio(selectedOwner)
      .then((p) => {
        setPortfolio(p);
        setError(null);
      })
      .catch(() => setError("Failed to load portfolio"))
      .finally(() => setLoading(false));
  }, [selectedOwner, retryNonce]);

  return (
    <div className="p-4 md:p-8">
      <SummaryBar
        owners={ownersReq.data ?? []}
        owner={selectedOwner}
        onOwnerChange={setSelectedOwner}
        onRefresh={() => setRetryNonce((n) => n + 1)}
      />
      <PortfolioView data={portfolio} loading={loading} error={error} />
    </div>
  );
}

export default Member;
