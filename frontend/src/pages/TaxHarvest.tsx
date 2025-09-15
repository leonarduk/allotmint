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

  const [ticker, setTicker] = useState("");
  const [basis, setBasis] = useState("");
  const [price, setPrice] = useState("");
  const [threshold, setThreshold] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleHarvest = async () => {
    setIsLoading(true);
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
          {trades.map(({ ticker, loss }, idx) => (
            <li key={idx}>
              {ticker}: {loss}
            </li>
          ))}
        </ul>
      )}
      {trades && trades.length === 0 && <p>No trades qualify</p>}
    </div>
  );
}
