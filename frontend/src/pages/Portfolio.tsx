import { useEffect, useState } from "react";
import { getPortfolio } from "../api";
import { PortfolioView } from "../components/PortfolioView";
import Meta from "../components/Meta";
import type { Portfolio as PortfolioData } from "../types";

export function Portfolio() {
  const [data, setData] = useState<PortfolioData | null>(null);
  useEffect(() => {
    getPortfolio("alice").then(setData).catch(() => setData(null));
  }, []);
  return (
    <>
      <Meta
        title="Portfolio"
        description="View and manage your investment portfolio"
        canonical="https://example.com/portfolio"
        jsonLd={{
          '@context': 'https://schema.org',
          '@type': 'WebPage',
          name: 'Portfolio',
          url: 'https://example.com/portfolio'
        }}
      />
      <PortfolioView data={data} />
    </>
  );
}

export default Portfolio;
