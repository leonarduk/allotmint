import { useState, useEffect } from "react";
import type { ChangeEvent } from "react";
import { getTimeseries, saveTimeseries, searchInstruments } from "../api";
import type { PriceEntry } from "../types";
import { EXCHANGES, type ExchangeCode } from "../lib/exchanges";

function parseCsv(text: string): PriceEntry[] {
  const lines = text.split(/\r?\n/).filter((l) => l.trim());
  if (!lines.length) return [];
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

  return rows.map<PriceEntry>((line) => {
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
      (
        obj as Record<keyof PriceEntry, PriceEntry[keyof PriceEntry]>
      )[key] = parsed as PriceEntry[typeof key];
    });
    return obj as PriceEntry;
  });
}

export function TimeseriesEdit() {
  const [ticker, setTicker] = useState("");
  const [exchange, setExchange] = useState<ExchangeCode>("L");
  const [rows, setRows] = useState<PriceEntry[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<
    { ticker: string; name: string }[]
  >([]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const t = params.get("ticker");
    const e = params.get("exchange");
    if (t) setTicker(t);
    if (e && EXCHANGES.includes(e as ExchangeCode)) {
      setExchange(e as ExchangeCode);
    }
  }, []);

  useEffect(() => {
    const trimmed = ticker.trim();
    if (trimmed.length < 2) {
      setSuggestions([]);
      return;
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => {
      searchInstruments(trimmed, undefined, undefined, controller.signal)
        .then(setSuggestions)
        .catch((err) => {
          if (err.name !== "AbortError") {
            console.error(err);
            setSuggestions([]);
          }
        });
    }, 300);
    return () => {
      controller.abort();
      clearTimeout(timeout);
    };
  }, [ticker]);

  async function handleLoad() {
    setError(null);
    try {
      const data = await getTimeseries(ticker, exchange);
      setRows(data);
      setStatus(`Loaded ${data.length} rows`);
    } catch (e) {
      setError(String(e));
    }
  }
  function handleFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = parseCsv(String(reader.result));
        setRows((prev) => {
          const map = new Map(prev.map((r) => [r.Date, r]));
          parsed.forEach((r) => map.set(r.Date, r));
          return Array.from(map.values());
        });
      } catch (err) {
        setError(String(err));
      }
    };
    reader.readAsText(file);
  }

  async function handleSave() {
    setError(null);
    try {
      if (!rows.length) throw new Error("No data to save");
      await saveTimeseries(ticker, exchange, rows);
      setStatus(`Saved ${rows.length} rows`);
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div className="container mx-auto p-4 max-w-3xl">
      <h2 className="mb-4 text-xl md:text-2xl">Timeseries Editor</h2>
      <div className="mb-2">
        <label>
          Ticker {" "}
          <input
            list="ticker-suggestions"
            value={ticker}
            onChange={(e) => {
              const val = e.target.value;
              const match = suggestions.find((s) => s.ticker === val);
              setTicker(match ? match.ticker : val);
            }}
          />
          <datalist id="ticker-suggestions">
            {suggestions.map((r) => (
              <option key={r.ticker} value={r.ticker}>
                {`${r.ticker} — ${r.name}`}
              </option>
            ))}
          </datalist>
        </label>{" "}
        <label>
          Exchange {" "}
          <select
            value={exchange}
            onChange={(e) => setExchange(e.target.value as ExchangeCode)}
            style={{ width: "4rem" }}
          >
            {EXCHANGES.map((ex) => (
              <option key={ex} value={ex}>
                {ex}
              </option>
            ))}
          </select>
        </label>{" "}
        <button onClick={handleLoad} disabled={!ticker}>
          Load
        </button>
      </div>
      <div className="mb-2 overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th>Date</th>
              <th>Open</th>
              <th>High</th>
              <th>Low</th>
              <th>Close</th>
              <th>Volume</th>
              <th>Ticker</th>
              <th>Source</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                <td>
                  <input
                    aria-label="Date"
                    value={row.Date}
                    onChange={(e) =>
                      setRows((rs) => {
                        const copy = [...rs];
                        copy[i] = { ...copy[i], Date: e.target.value };
                        return copy;
                      })
                    }
                  />
                </td>
                <td>
                  <input
                    aria-label="Open"
                    type="number"
                    value={row.Open ?? ""}
                    onChange={(e) =>
                      setRows((rs) => {
                        const copy = [...rs];
                        copy[i] = {
                          ...copy[i],
                          Open: e.target.value === "" ? null : Number(e.target.value),
                        };
                        return copy;
                      })
                    }
                  />
                </td>
                <td>
                  <input
                    aria-label="High"
                    type="number"
                    value={row.High ?? ""}
                    onChange={(e) =>
                      setRows((rs) => {
                        const copy = [...rs];
                        copy[i] = {
                          ...copy[i],
                          High: e.target.value === "" ? null : Number(e.target.value),
                        };
                        return copy;
                      })
                    }
                  />
                </td>
                <td>
                  <input
                    aria-label="Low"
                    type="number"
                    value={row.Low ?? ""}
                    onChange={(e) =>
                      setRows((rs) => {
                        const copy = [...rs];
                        copy[i] = {
                          ...copy[i],
                          Low: e.target.value === "" ? null : Number(e.target.value),
                        };
                        return copy;
                      })
                    }
                  />
                </td>
                <td>
                  <input
                    aria-label="Close"
                    type="number"
                    value={row.Close ?? ""}
                    onChange={(e) =>
                      setRows((rs) => {
                        const copy = [...rs];
                        copy[i] = {
                          ...copy[i],
                          Close: e.target.value === "" ? null : Number(e.target.value),
                        };
                        return copy;
                      })
                    }
                  />
                </td>
                <td>
                  <input
                    aria-label="Volume"
                    type="number"
                    value={row.Volume ?? ""}
                    onChange={(e) =>
                      setRows((rs) => {
                        const copy = [...rs];
                        copy[i] = {
                          ...copy[i],
                          Volume: e.target.value === "" ? null : Number(e.target.value),
                        };
                        return copy;
                      })
                    }
                  />
                </td>
                <td>
                  <input
                    aria-label="Ticker"
                    value={row.Ticker ?? ""}
                    onChange={(e) =>
                      setRows((rs) => {
                        const copy = [...rs];
                        copy[i] = { ...copy[i], Ticker: e.target.value };
                        return copy;
                      })
                    }
                  />
                </td>
                <td>
                  <input
                    aria-label="Source"
                    value={row.Source ?? ""}
                    onChange={(e) =>
                      setRows((rs) => {
                        const copy = [...rs];
                        copy[i] = { ...copy[i], Source: e.target.value };
                        return copy;
                      })
                    }
                  />
                </td>
                <td>
                  <button
                    aria-label="Delete"
                    onClick={() =>
                      setRows((rs) => rs.filter((_, idx) => idx !== i))
                    }
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ marginBottom: "0.5rem" }}>
        <button
          onClick={() =>
            setRows((rs) => [
              ...rs,
              {
                Date: "",
                Open: null,
                High: null,
                Low: null,
                Close: null,
                Volume: null,
                Ticker: "",
                Source: "",
              },
            ])
          }
        >
          Add Row
        </button>
      </div>
      <div style={{ marginBottom: "0.5rem" }}>
        <input type="file" accept=".csv" onChange={handleFile} />{" "}
        <button onClick={handleSave} disabled={!ticker || !rows.length}>
          Save
        </button>
      </div>
      {status && <p style={{ color: "green" }}>{status}</p>}
      {error && <p style={{ color: "red" }}>{error}</p>}
    </div>
  );
}
