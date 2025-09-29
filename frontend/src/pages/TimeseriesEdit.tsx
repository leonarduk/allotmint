import { useState, useEffect, useRef, useMemo } from "react";
import type { ChangeEvent } from "react";
import {
  getInstrumentMetadata,
  getTimeseries,
  saveTimeseries,
  searchInstruments,
} from "../api";
import type { InstrumentMetadata, PriceEntry } from "../types";
import { EXCHANGES, type ExchangeCode } from "../lib/exchanges";
import { useTranslation } from "react-i18next";
import i18next from "i18next";

function parseCsv(
  text: string,
): { rows: PriceEntry[]; error: string | null } {
  try {
    const lines = text.split(/\r?\n/).filter((l) => l.trim());
    if (!lines.length) {
      return { rows: [], error: null };
    }
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
    if (unexpected.length) {
      return {
        rows: [],
        error: i18next.t("timeseriesEdit.error.unexpectedColumns", {
          columns: unexpected.join(", "),
        }),
      };
    }

    return {
      rows: rows.map<PriceEntry>((line) => {
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
      }),
      error: null,
    };
  } catch (err) {
    console.error("Failed to parse CSV", err);
    return {
      rows: [],
      error: err instanceof Error ? err.message : String(err),
    };
  }
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

  const [scaleFactor, setScaleFactor] = useState<string>("1");
  const [scaleVolume, setScaleVolume] = useState(false);
  const userScaleEditedRef = useRef(false);
  const lastInstrumentKeyRef = useRef<string | null>(null);

  const [sortDirection, setSortDirection] = useState<"asc" | "desc">(
    "desc",
  );
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const safeRows = Array.isArray(rows) ? rows : [];
  const safeSuggestions = Array.isArray(suggestions) ? suggestions : [];


  const numberFormatter = useMemo(
    () =>
      new Intl.NumberFormat(undefined, {
        maximumFractionDigits: 8,
        useGrouping: false,
      }),
    [],
  );

  const sortedRows = useMemo(() => {
    const baseRows = Array.isArray(rows) ? rows : [];
    const toTimestamp = (value: string | undefined) => {
      if (!value) return NaN;
      const parsed = Date.parse(value);
      return Number.isNaN(parsed) ? NaN : parsed;
    };
    const directionMultiplier = sortDirection === "asc" ? 1 : -1;
    return baseRows
      .map((row, index) => ({ row, index }))
      .sort((a, b) => {
        const aTime = toTimestamp(a.row.Date);
        const bTime = toTimestamp(b.row.Date);
        const aInvalid = Number.isNaN(aTime);
        const bInvalid = Number.isNaN(bTime);
        if (aInvalid && bInvalid) return 0;
        if (aInvalid) return 1;
        if (bInvalid) return -1;
        return (aTime - bTime) * directionMultiplier;
      });
  }, [rows, sortDirection]);

  const displayRows = useMemo(() => {
    const start = startDate ? Date.parse(startDate) : null;
    const end = endDate ? Date.parse(endDate) : null;
    return sortedRows.filter(({ row }) => {
      const timestamp = row.Date ? Date.parse(row.Date) : NaN;
      const isValidTimestamp = !Number.isNaN(timestamp);
      if (start !== null && (!isValidTimestamp || timestamp < start)) {
        return false;
      }
      if (end !== null && (!isValidTimestamp || timestamp > end)) {
        return false;
      }
      return true;
    });
  }, [sortedRows, startDate, endDate]);

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
      Promise.resolve(
        searchInstruments(trimmed, undefined, undefined, controller.signal) as
          | Promise<{ ticker: string; name: string }[]>
          | { ticker: string; name: string }[]
          | undefined,
      )
        .then((res) => setSuggestions(Array.isArray(res) ? res : []))
        .catch((err: any) => {
          if (err?.name !== "AbortError") {
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

  useEffect(() => {
    const trimmed = ticker.trim();
    if (!trimmed) {
      lastInstrumentKeyRef.current = null;
      return;
    }
    const instrumentKey = `${trimmed.toUpperCase()}|${exchange}`;
    if (instrumentKey !== lastInstrumentKeyRef.current) {
      userScaleEditedRef.current = false;
      lastInstrumentKeyRef.current = instrumentKey;
    }

    let ignore = false;
    const baseTicker = trimmed.split(".")[0] || trimmed;
    Promise.resolve(
      getInstrumentMetadata(baseTicker, exchange) as Promise<
        (InstrumentMetadata & Record<string, unknown>) |
          Record<string, unknown> |
          null
      >,
    )
      .then((meta) => {
        if (ignore || !meta || typeof meta !== "object") return;
        const possible = [
          meta["price_scaling"],
          meta["priceScaling"],
          meta["scaling"],
          meta["scale"],
        ];
        let suggestion: number | null = null;
        for (const value of possible) {
          if (value == null) continue;
          const parsed = Number(value);
          if (!Number.isNaN(parsed) && parsed > 0) {
            suggestion = parsed;
            break;
          }
        }
        if (suggestion == null) {
          let detectedCurrency: string | null = null;
          const topCurrency = meta["currency"] ?? meta["Currency"];
          if (typeof topCurrency === "string") {
            detectedCurrency = topCurrency;
          } else {
            const metaRecord = meta as Record<string, unknown>;
            for (const nestedKey of ["price", "quote"]) {
              const block = metaRecord[nestedKey];
              if (block && typeof block === "object") {
                const nested = block as Record<string, unknown>;
                const nestedCurrency =
                  nested["currency"] ?? nested["Currency"] ?? null;
                if (typeof nestedCurrency === "string") {
                  detectedCurrency = nestedCurrency;
                  break;
                }
              }
            }
          }
          if (detectedCurrency) {
            const normalized = detectedCurrency.trim().toUpperCase();
            if (normalized === "GBX" || normalized === "GBXP" || normalized === "GBPX") {
              suggestion = 0.01;
            }
          }
        }
        if (
          suggestion != null &&
          !Number.isNaN(suggestion) &&
          suggestion > 0 &&
          !userScaleEditedRef.current
        ) {
          setScaleFactor((current) => {
            if (current && current.trim() !== "" && current !== "1") {
              return current;
            }
            return String(suggestion);
          });
        }
      })
      .catch((err: unknown) => {
        if ((err as { status?: number })?.status !== 404) {
          console.debug("Failed to fetch instrument metadata", err);
        }
      });
    return () => {
      ignore = true;
    };
  }, [ticker, exchange]);

  async function handleLoad() {
    setError(null);
    try {
      const data = (await getTimeseries(ticker, exchange)) ?? [];
      const arr = Array.isArray(data) ? data : [];
      setRows(arr);
      setStatus(t("timeseriesEdit.status.loaded", { count: arr.length }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  function handleFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const { rows: parsed, error: parseError } = parseCsv(
          String(reader.result),
        );
        if (parseError) {
          setError(parseError);
          return;
        }
        setError(null);
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
      const entries = sortedRows.map(({ row }) => row);
      if (!entries.length)
        throw new Error(t("timeseriesEdit.error.noData"));
      await saveTimeseries(ticker, exchange, entries);
      setStatus(t("timeseriesEdit.status.saved", { count: entries.length }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function handleApplyScaling() {
    const parsed = Number(scaleFactor);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setError(t("timeseriesEdit.error.invalidScale"));
      return;
    }
    if (!safeRows.length) {
      setError(t("timeseriesEdit.error.noData"));
      return;
    }
    setError(null);
    const scaledRows = safeRows.map((entry) => {
      const scaleValue = <T extends number | null | undefined>(value: T): T => {
        if (value == null) {
          return value;
        }
        const numeric = Number(value);
        if (!Number.isFinite(numeric)) {
          return value;
        }
        const result = numeric * parsed;
        return (Number.isFinite(result) ? (result as T) : value) as T;
      };
      return {
        ...entry,
        Open: scaleValue(entry.Open),
        High: scaleValue(entry.High),
        Low: scaleValue(entry.Low),
        Close: scaleValue(entry.Close),
        Volume: scaleVolume ? scaleValue(entry.Volume) : entry.Volume ?? null,
      };
    });
    setRows(scaledRows);
    const formattedFactor = numberFormatter.format(parsed);
    const volumeNote = scaleVolume
      ? t("timeseriesEdit.status.volumeIncluded")
      : "";
    setStatus(
      t("timeseriesEdit.status.scaled", {
        factor: formattedFactor,
        count: scaledRows.length,
        volumeNote,
      }),
    );
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
              const match = safeSuggestions.find((s) => s.ticker === val);
              setTicker(match ? match.ticker : val);
            }}
          />
          <datalist id="ticker-suggestions">
            {safeSuggestions.map((r) => (
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
      <div className="mb-3 flex flex-wrap items-end gap-4 text-sm">
        <label className="flex flex-col gap-1">
          <span>
            {t("timeseriesEdit.controls.sort", { defaultValue: "Sort" })}
          </span>
          <select
            value={sortDirection}
            onChange={(e) =>
              setSortDirection(e.target.value as "asc" | "desc")
            }
          >
            <option value="desc">
              {t("timeseriesEdit.controls.sortDesc", {
                defaultValue: "Newest first",
              })}
            </option>
            <option value="asc">
              {t("timeseriesEdit.controls.sortAsc", {
                defaultValue: "Oldest first",
              })}
            </option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span>
            {t("timeseriesEdit.controls.startDate", {
              defaultValue: "Start date",
            })}
          </span>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span>
            {t("timeseriesEdit.controls.endDate", {
              defaultValue: "End date",
            })}
          </span>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
          />
        </label>
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
            {displayRows.map(({ row, index: originalIndex }) => (
              <tr key={`${originalIndex}-${row.Date ?? "row"}`}>
                <td>
                  <input
                    aria-label={t("timeseriesEdit.columns.date")}
                    value={row.Date}
                    onChange={(e) =>
                      setRows((rs) => {
                        const copy = [...rs];
                        copy[originalIndex] = {
                          ...copy[originalIndex],
                          Date: e.target.value,
                        };
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
                        copy[originalIndex] = {
                          ...copy[originalIndex],
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
                        copy[originalIndex] = {
                          ...copy[originalIndex],
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
                        copy[originalIndex] = {
                          ...copy[originalIndex],
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
                        copy[originalIndex] = {
                          ...copy[originalIndex],
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
                        copy[originalIndex] = {
                          ...copy[originalIndex],
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
                        copy[originalIndex] = {
                          ...copy[originalIndex],
                          Ticker: e.target.value,
                        };
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
                        copy[originalIndex] = {
                          ...copy[originalIndex],
                          Source: e.target.value,
                        };
                        return copy;
                      })
                    }
                  />
                </td>
                <td>
                  <button
                    aria-label={t("timeseriesEdit.delete")}
                    onClick={() =>
                      setRows((rs) =>
                        rs.filter((_, idx) => idx !== originalIndex),
                      )
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
        <button onClick={handleSave} disabled={!ticker || !safeRows.length}>
          {t("timeseriesEdit.save")}
        </button>
      </div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <label>
          {t("timeseriesEdit.scaleFactor")}{" "}
          <input
            type="number"
            inputMode="decimal"
            step="any"
            value={scaleFactor}
            onChange={(e) => {
              userScaleEditedRef.current = true;
              setScaleFactor(e.target.value);
            }}
            style={{ width: "6rem" }}
          />
        </label>
        <label className="flex items-center gap-1">
          <input
            type="checkbox"
            checked={scaleVolume}
            onChange={(e) => setScaleVolume(e.target.checked)}
          />
          {t("timeseriesEdit.scaleVolume")}
        </label>
        <button onClick={handleApplyScaling} disabled={!safeRows.length}>
          {t("timeseriesEdit.applyScaling")}
        </button>
      </div>
      {status && <p style={{ color: "green" }}>{status}</p>}
      {error && <p style={{ color: "red" }}>{error}</p>}
    </div>
  );
}
