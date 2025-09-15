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

  const [ticker, setTicker] = useState("");
  const [basis, setBasis] = useState("");
  const [price, setPrice] = useState("");
  const [threshold, setThreshold] = useState("");

  const handleHarvest = async () => {
    try {
      const positions: Position[] = [
        {
          ticker,
          basis: parseFloat(basis),
          price: parseFloat(price),
        },
      ];
      const res = await harvestTax(positions, parseFloat(threshold));
      setTrades(res.trades);
      setError(null);
    } catch {
      setError("Failed to harvest");
      setTrades(null);
    }
  };

  return (
    <div>
      <h1 className="mb-4 text-2xl md:text-4xl">Tax Harvest</h1>
      <div className="mb-4 flex flex-col gap-2 max-w-sm">
        <input
          placeholder="Ticker"
          className="rounded border px-2 py-1"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
        />
        <input
          placeholder="Basis"
          type="number"
          className="rounded border px-2 py-1"
          value={basis}
          onChange={(e) => setBasis(e.target.value)}
        />
        <input
          placeholder="Price"
          type="number"
          className="rounded border px-2 py-1"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
        />
        <input
          placeholder="Threshold"
          type="number"
          className="rounded border px-2 py-1"
          value={threshold}
          onChange={(e) => setThreshold(e.target.value)}
        />
      </div>
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
          {trades.map((t, idx) => (
            <li key={idx}>{JSON.stringify(t)}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
