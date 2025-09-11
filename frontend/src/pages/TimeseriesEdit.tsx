import { useState, useEffect } from "react";
import type { ChangeEvent } from "react";
import { getTimeseries, saveTimeseries, searchInstruments } from "../api";
import type { PriceEntry } from "../types";
import { EXCHANGES, type ExchangeCode } from "../lib/exchanges";
import { useTranslation } from "react-i18next";
import i18next from "i18next";

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
    throw new Error(
      i18next.t("timeseriesEdit.error.unexpectedColumns", {
        columns: unexpected.join(", "),
      }),
    );

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
  const { t } = useTranslation();
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
    const tickerParam = params.get("ticker");
    const e = params.get("exchange");
    if (tickerParam) setTicker(tickerParam);
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
      const data = (await getTimeseries(ticker, exchange)) ?? [];
      const arr = Array.isArray(data) ? data : [];
      setRows(arr);
      setStatus(t("timeseriesEdit.status.loaded", { count: arr.length }));
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
      if (!rows.length)
        throw new Error(t("timeseriesEdit.error.noData"));
      await saveTimeseries(ticker, exchange, rows);
      setStatus(t("timeseriesEdit.status.saved", { count: rows.length }));
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div className="container mx-auto p-4 max-w-3xl">
      <h2 className="mb-4 text-xl md:text-2xl">
        {t("timeseriesEdit.title")}
      </h2>
      <div className="mb-2">
        <label>
          {t("timeseriesEdit.ticker")}{" "}
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
          {t("timeseriesEdit.exchange")}{" "}
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
          {t("timeseriesEdit.load")}
        </button>
      </div>
      <div className="mb-2 overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th>{t("timeseriesEdit.columns.date")}</th>
              <th>{t("timeseriesEdit.columns.open")}</th>
              <th>{t("timeseriesEdit.columns.high")}</th>
              <th>{t("timeseriesEdit.columns.low")}</th>
              <th>{t("timeseriesEdit.columns.close")}</th>
              <th>{t("timeseriesEdit.columns.volume")}</th>
              <th>{t("timeseriesEdit.columns.ticker")}</th>
              <th>{t("timeseriesEdit.columns.source")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(Array.isArray(rows) ? rows : []).map((row, i) => (
              <tr key={i}>
                <td>
                  <input
                    aria-label={t("timeseriesEdit.columns.date")}
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
                    aria-label={t("timeseriesEdit.columns.open")}
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
                    aria-label={t("timeseriesEdit.columns.high")}
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
                    aria-label={t("timeseriesEdit.columns.low")}
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
                    aria-label={t("timeseriesEdit.columns.close")}
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
                    aria-label={t("timeseriesEdit.columns.volume")}
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
                    aria-label={t("timeseriesEdit.columns.ticker")}
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
                    aria-label={t("timeseriesEdit.columns.source")}
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
                    aria-label={t("timeseriesEdit.delete")}
                    onClick={() =>
                      setRows((rs) => rs.filter((_, idx) => idx !== i))
                    }
                  >
                    {t("timeseriesEdit.delete")}
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
          {t("timeseriesEdit.addRow")}
        </button>
      </div>
      <div style={{ marginBottom: "0.5rem" }}>
        <input type="file" accept=".csv" onChange={handleFile} />{" "}
        <button onClick={handleSave} disabled={!ticker || !rows.length}>
          {t("timeseriesEdit.save")}
        </button>
      </div>
      {status && <p style={{ color: "green" }}>{status}</p>}
      {error && <p style={{ color: "red" }}>{error}</p>}
    </div>
  );
}
