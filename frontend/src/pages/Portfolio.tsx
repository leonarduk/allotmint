import { useEffect, useState } from "react";
import { getPortfolio } from "../api";
import { PortfolioView } from "../components/PortfolioView";
import type { Portfolio } from "../types";

export function Portfolio() {
  const [data, setData] = useState<Portfolio | null>(null);
  useEffect(() => {
    getPortfolio("alice").then(setData).catch(() => setData(null));
  }, []);
  return <PortfolioView data={data} />;
}

export default Portfolio;
