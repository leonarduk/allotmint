import { useState, useEffect } from "react";
import type { ChangeEvent } from "react";
import { getTimeseries, saveTimeseries } from "../api";
import type { PriceEntry } from "../types";

export function TimeseriesEdit() {
  const [ticker, setTicker] = useState("");
  const [exchange, setExchange] = useState("L");
  const [csv, setCsv] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const t = params.get("ticker");
    const e = params.get("exchange");
    if (t) setTicker(t);
    if (e) setExchange(e);
  }, []);

  async function handleLoad() {
    setError(null);
    try {
      const rows = await getTimeseries(ticker, exchange);
      const header = "Date,Open,High,Low,Close,Volume";
      const lines = rows.map(
        (r) =>
          `${r.Date},${r.Open ?? ""},${r.High ?? ""},${r.Low ?? ""},${r.Close ?? ""},${r.Volume ?? ""}`
      );
      setCsv([header, ...lines].join("\n"));
      setStatus(`Loaded ${rows.length} rows`);
    } catch (e) {
      setError(String(e));
    }
  }

  function handleFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setCsv(String(reader.result));
    reader.readAsText(file);
  }

  async function handleSave() {
    setError(null);
    try {
      const lines = csv.split(/\r?\n/).filter((l) => l.trim());
      if (!lines.length) throw new Error("No data to save");
      const [header, ...rows] = lines;
      const cols = header.split(",");
      const allowedCols: (keyof PriceEntry)[] = [
        "Date",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
        "Ticker",
        "Source",
      ];
      const unexpected = cols.filter(
        (c) => !allowedCols.includes(c as keyof PriceEntry),
      );
      if (unexpected.length)
        throw new Error(`Unexpected column(s): ${unexpected.join(", ")}`);

      const data = rows.map<PriceEntry>((line) => {
        const parts = line.split(",");
        const obj: Partial<PriceEntry> = {};
        cols.forEach((col, i) => {
          const key = col as keyof PriceEntry;
          const val = parts[i];
          const parsed =
            key === "Date" || key === "Ticker" || key === "Source"
              ? val
              : val === undefined || val === ""
              ? null
              : Number(val);
          obj[key] = parsed as PriceEntry[typeof key];
        });
        return obj as PriceEntry;
      });
      await saveTimeseries(ticker, exchange, data);
      setStatus(`Saved ${data.length} rows`);
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
      <h2>Timeseries Editor</h2>
      <div style={{ marginBottom: "0.5rem" }}>
        <label>
          Ticker {" "}
          <input value={ticker} onChange={(e) => setTicker(e.target.value)} />
        </label>{" "}
        <label>
          Exchange {" "}
          <input
            value={exchange}
            onChange={(e) => setExchange(e.target.value)}
            style={{ width: "4rem" }}
          />
        </label>{" "}
        <button onClick={handleLoad} disabled={!ticker}>
          Load
        </button>
      </div>
      <div style={{ marginBottom: "0.5rem" }}>
        <textarea
          value={csv}
          onChange={(e) => setCsv(e.target.value)}
          rows={20}
          style={{ width: "100%" }}
          placeholder="Date,Open,High,Low,Close,Volume"
        />
      </div>
      <div style={{ marginBottom: "0.5rem" }}>
        <input type="file" accept=".csv" onChange={handleFile} />{" "}
        <button onClick={handleSave} disabled={!ticker || !csv.trim()}>
          Save
        </button>
      </div>
      {status && <p style={{ color: "green" }}>{status}</p>}
      {error && <p style={{ color: "red" }}>{error}</p>}
    </div>
  );
}
