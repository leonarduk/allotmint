import { useEffect, useState } from "react";
import { getPortfolio } from "../api";
import { PortfolioView } from "../components/PortfolioView";
import Meta from "../components/Meta";
import type { Portfolio as PortfolioData } from "../types";

export function Portfolio() {
  const [data, setData] = useState<PortfolioData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const BASE_URL = import.meta.env.VITE_APP_BASE_URL || "https://app.allotmint.io";

  useEffect(() => {
    getPortfolio("alice")
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch(() => setError("Failed to load portfolio"))
      .finally(() => setLoading(false));
  }, []);
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
