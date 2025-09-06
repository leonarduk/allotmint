import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getPortfolio } from "../api";
import { PortfolioView } from "../components/PortfolioView";
import Meta from "../components/Meta";
import { useRoute } from "../RouteContext";
import type { Portfolio as PortfolioData } from "../types";

export function Portfolio() {
  const [data, setData] = useState<PortfolioData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const BASE_URL = import.meta.env.VITE_APP_BASE_URL || "https://app.allotmint.io";

  const { owner: ownerParam } = useParams<{ owner?: string }>();
  let owner = ownerParam;
  try {
    const { selectedOwner } = useRoute();
    if (!owner) owner = selectedOwner;
  } catch {
    /* Route context not available */
  }

  useEffect(() => {
    if (!owner) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    setData(null);
    getPortfolio(owner)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch(() => setError("Failed to load portfolio"))
      .finally(() => setLoading(false));
  }, [owner]);
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
          image: `${BASE_URL}/vite.svg`
        }}
      />
      <PortfolioView data={data} loading={loading} error={error} />
    </>
  );
}

export default Portfolio;
