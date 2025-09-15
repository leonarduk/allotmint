import { useState } from "react";
import { harvestTax } from "../api";

interface Position {
  ticker: string;
  basis: number;
  price: number;
}

interface Trade {
  ticker: string;
  loss: number;
}

export default function TaxHarvest() {
  const [trades, setTrades] = useState<Trade[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const samplePositions: Position[] = [
    { ticker: "ABC", basis: 100, price: 80 },
    { ticker: "XYZ", basis: 200, price: 150 },
  ];

  const handleHarvest = async () => {
    try {
      const res = await harvestTax(samplePositions, 0);
      setTrades(res.trades);
      setError(null);
    } catch (e) {
      setError("Failed to harvest");
      setTrades(null);
    }
  };

  return (
    <div>
      <h1 className="mb-4 text-2xl md:text-4xl">Tax Harvest</h1>
      <button
        type="button"
        className="mb-4 rounded border px-4 py-2"
        onClick={handleHarvest}
      >
        Run Harvest
      </button>
      {error && <p className="text-red-500">{error}</p>}
      {trades && (
        <ul data-testid="harvest-results">
          {trades.map(({ ticker, loss }, idx) => (
            <li key={idx}>
              {ticker}: {loss}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
