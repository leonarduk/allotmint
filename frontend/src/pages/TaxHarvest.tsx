import { useState } from "react";
import { harvestTax } from "../api";

interface Position {
  ticker: string;
  basis: number;
  price: number;
}

export default function TaxHarvest() {
  const [trades, setTrades] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const samplePositions: Position[] = [
    { ticker: "ABC", basis: 100, price: 80 },
    { ticker: "XYZ", basis: 200, price: 150 },
  ];

  const handleHarvest = async () => {
    setIsLoading(true);
    try {
      const res = await harvestTax(samplePositions, 0);
      setTrades(res.trades);
      setError(null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setTrades(null);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div>
      <h1 className="mb-4 text-2xl md:text-4xl">Tax Harvest</h1>
      <button
        type="button"
        className="mb-4 rounded border px-4 py-2"
        onClick={handleHarvest}
        disabled={isLoading}
      >
        Run Harvest
      </button>
      {isLoading && (
        <div data-testid="spinner">Loading...</div>
      )}
      {error && <p className="text-red-500">{error}</p>}
      {trades && trades.length > 0 && (
        <ul data-testid="harvest-results">
          {trades.map((t, idx) => (
            <li key={idx}>{JSON.stringify(t)}</li>
          ))}
        </ul>
      )}
      {trades && trades.length === 0 && <p>No trades qualify</p>}
    </div>
  );
}
