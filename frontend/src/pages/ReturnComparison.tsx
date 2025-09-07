import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getReturnComparison } from "../api";
import { percent } from "../lib/money";

const OPTIONS = [
  { label: "1Y", days: 365 },
  { label: "3Y", days: 365 * 3 },
  { label: "5Y", days: 365 * 5 },
];

export default function ReturnComparison() {
  const [searchParams] = useSearchParams();
  const owner = searchParams.get("owner") || "";
  const [days, setDays] = useState(365);
  const [cagr, setCagr] = useState<number | null>(null);
  const [cashApy, setCashApy] = useState<number | null>(null);

  useEffect(() => {
    if (!owner) return;
    getReturnComparison(owner, days).then((res) => {
      setCagr(res.cagr);
      setCashApy(res.cash_apy);
    });
  }, [owner, days]);

  return (
    <div className="p-4">
      <h1>Return Comparison – {owner}</h1>
      <label className="block mb-4">
        Timeframe:
        <select
          className="ml-2"
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
        >
          {OPTIONS.map((o) => (
            <option key={o.days} value={o.days}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
      <ul>
        <li>Portfolio CAGR: {percent(cagr != null ? cagr * 100 : null)}</li>
        <li>Cash APY: {percent(cashApy != null ? cashApy * 100 : null)}</li>
      </ul>
    </div>
  );
}
