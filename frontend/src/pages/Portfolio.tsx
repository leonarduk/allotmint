import { useEffect, useState } from "react";
import { getPortfolio } from "../api";
import { PortfolioView } from "../components/PortfolioView";
import type { Portfolio as PortfolioData } from "../types";

export function Portfolio() {
  const [data, setData] = useState<PortfolioData | null>(null);
  useEffect(() => {
    getPortfolio("alice").then(setData).catch(() => setData(null));
  }, []);
  return <PortfolioView data={data} />;
}

export default Portfolio;
