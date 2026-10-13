import { useState, useEffect, useId, useRef, useMemo } from "react";
import type { ChangeEvent } from "react";
import {
  getInstrumentMetadata,
  getTimeseries,
  moveTimeseries,
  saveTimeseries,
  searchInstruments,
} from "../api";
import type { InstrumentMetadata, PriceEntry } from "../types";
import { EXCHANGES, type ExchangeCode } from "../lib/exchanges";
import { useTranslation } from "react-i18next";
import i18next from "i18next";

/**
 * Rows rendered per page of the editable grid. Each row is 8 inputs plus a
 * Delete button, so 50 rows keeps the grid at 400 inputs however long the
 * loaded series is (#10825).
 */
export const TIMESERIES_PAGE_SIZE = 50;

type GridColumn = {
  field: keyof PriceEntry;
  labelKey: string;
  numeric: boolean;
};

const GRID_COLUMNS: GridColumn[] = [
  { field: "Date", labelKey: "timeseriesEdit.columns.date", numeric: false },
  { field: "Open", labelKey: "timeseriesEdit.columns.open", numeric: true },
  { field: "High", labelKey: "timeseriesEdit.columns.high", numeric: true },
  { field: "Low", labelKey: "timeseriesEdit.columns.low", numeric: true },
  { field: "Close", labelKey: "timeseriesEdit.columns.close", numeric: true },
  { field: "Volume", labelKey: "timeseriesEdit.columns.volume", numeric: true },
  { field: "Ticker", labelKey: "timeseriesEdit.columns.ticker", numeric: false },
  { field: "Source", labelKey: "timeseriesEdit.columns.source", numeric: false },
];

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
  const [loadedSeries, setLoadedSeries] = useState<{
    ticker: string;
    exchange: ExchangeCode;
  } | null>(null);
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
  const [page, setPage] = useState(0);
  const tickerInputId = useId();
  const exchangeSelectId = useId();
  const startDateId = useId();
  const endDateId = useId();

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

  const pageCount = Math.max(
    1,
    Math.ceil(displayRows.length / TIMESERIES_PAGE_SIZE),
  );
  // Clamp rather than reset so deleting a row keeps the user on the page they
  // were editing instead of jumping back to page 1.
  const currentPage = Math.min(page, pageCount - 1);
  const pageStart = currentPage * TIMESERIES_PAGE_SIZE;
  const pageRows = displayRows.slice(
    pageStart,
    pageStart + TIMESERIES_PAGE_SIZE,
  );

  function updateCell(
    index: number,
    field: keyof PriceEntry,
    raw: string,
    numeric: boolean,
  ) {
    const value = numeric ? (raw === "" ? null : Number(raw)) : raw;
    setRows((rs) => {
      const copy = [...rs];
      copy[index] = { ...copy[index], [field]: value };
      return copy;
    });
  }

  function cellLabel(column: string, row: PriceEntry, rowNumber: number) {
    return row.Date
      ? t("timeseriesEdit.grid.cellLabel", { column, date: row.Date })
      : t("timeseriesEdit.grid.cellLabelUndated", { column, row: rowNumber });
  }

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
      setPage(0);
      // Record the load attempt even when the series is empty so the Move
      // action stays available: an empty source cannot be moved, but the
      // user must be able to attempt it and see the actionable error (#6723).
      setLoadedSeries({ ticker, exchange });
      setStatus(
        arr.length
          ? t("timeseriesEdit.status.loaded", { count: arr.length })
          : t("timeseriesEdit.status.noData", { ticker, exchange }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleMove() {
    if (!loadedSeries || loadedSeries.ticker !== ticker || loadedSeries.exchange === exchange) return;
    const source = loadedSeries.exchange;
    setError(null);
    try {
      await moveTimeseries(ticker, source, exchange);
      const data = (await getTimeseries(ticker, exchange)) ?? [];
      const arr = Array.isArray(data) ? data : [];
      setRows(arr);
      setLoadedSeries(arr.length ? { ticker, exchange } : null);
      setStatus(
        t("timeseriesEdit.status.moved", {
          ticker,
          source,
          destination: exchange,
        }),
      );
    } catch (e) {
      setLoadedSeries(null);
      setRows([]);
      const status = (e as { status?: number })?.status;
      if (status === 404) {
        // Empty/missing source: nothing to move; tell the user how to fix
        // the holding so the fetcher can populate the destination (#6723).
        setError(
          t("timeseriesEdit.error.moveNoData", {
            ticker,
            source,
            destination: exchange,
          }),
        );
      } else if (status === 409) {
        setError(t("timeseriesEdit.status.moveConflict", { exchange }));
      } else {
        setError(e instanceof Error ? e.message : String(e));
      }
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
        <label htmlFor={tickerInputId}>
          {t("timeseriesEdit.ticker")}{" "}
          <input
            id={tickerInputId}
            aria-label={t("timeseriesEdit.ticker")}
            list="ticker-suggestions"
            value={ticker}
            onChange={(e) => {
              const val = e.target.value;
              const match = safeSuggestions.find((s) => s.ticker === val);
              setTicker(match ? match.ticker : val);
            }}
          />
          <datalist id="ticker-suggestions">
            {safeSuggestions.map((r, index) => (
              <option key={`${r.ticker}-${index}`} value={r.ticker}>
                {`${r.ticker} — ${r.name}`}
              </option>
            ))}
          </datalist>
        </label>{" "}
        <label htmlFor={exchangeSelectId}>
          {t("timeseriesEdit.exchange")}{" "}
          <select
            id={exchangeSelectId}
            aria-label={t("timeseriesEdit.exchange")}
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
        <button data-testid="load-button" onClick={handleLoad} disabled={!ticker}>
          {t("timeseriesEdit.load")}
        </button>
        <button
          data-testid="move-button"
          onClick={handleMove}
          disabled={
            !loadedSeries ||
            loadedSeries.ticker !== ticker ||
            loadedSeries.exchange === exchange
          }
          title={t("timeseriesEdit.moveHelp")}
        >
          {t("timeseriesEdit.move", { exchange })}
        </button>
      </div>
      <div className="mb-3 flex flex-wrap items-end gap-4 text-sm">
        <label className="flex flex-col gap-1">
          <span>
            {t("timeseriesEdit.controls.sort", { defaultValue: "Sort" })}
          </span>
          <select
            value={sortDirection}
            onChange={(e) => {
              setSortDirection(e.target.value as "asc" | "desc");
              setPage(0);
            }}
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
        <label className="flex flex-col gap-1" htmlFor={startDateId}>
          <span>
            {t("timeseriesEdit.controls.startDate", {
              defaultValue: "Start date",
            })}
          </span>
          <input
            id={startDateId}
            aria-label={t("timeseriesEdit.controls.startDate", {
              defaultValue: "Start date",
            })}
            type="date"
            value={startDate}
            onChange={(e) => {
              setStartDate(e.target.value);
              setPage(0);
            }}
          />
        </label>
        <label className="flex flex-col gap-1" htmlFor={endDateId}>
          <span>
            {t("timeseriesEdit.controls.endDate", {
              defaultValue: "End date",
            })}
          </span>
          <input
            id={endDateId}
            aria-label={t("timeseriesEdit.controls.endDate", {
              defaultValue: "End date",
            })}
            type="date"
            value={endDate}
            onChange={(e) => {
              setEndDate(e.target.value);
              setPage(0);
            }}
          />
        </label>
      </div>
      <div className="mb-2 overflow-x-auto">
        <table
          className="w-full border-collapse"
          aria-label={t("timeseriesEdit.grid.rowsLabel")}
        >
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
            {pageRows.map(({ row, index: originalIndex }, offset) => {
              const rowNumber = pageStart + offset + 1;
              return (
                <tr key={`${originalIndex}-${row.Date ?? "row"}`}>
                  {GRID_COLUMNS.map(({ field, labelKey, numeric }) => (
                    <td key={field}>
                      <input
                        aria-label={cellLabel(t(labelKey), row, rowNumber)}
                        type={numeric ? "number" : undefined}
                        value={row[field] ?? ""}
                        onChange={(e) =>
                          updateCell(
                            originalIndex,
                            field,
                            e.target.value,
                            numeric,
                          )
                        }
                      />
                    </td>
                  ))}
                  <td>
                    <button
                      aria-label={cellLabel(
                        t("timeseriesEdit.delete"),
                        row,
                        rowNumber,
                      )}
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
              );
            })}
          </tbody>
        </table>
      </div>
      {displayRows.length > TIMESERIES_PAGE_SIZE && (
        <nav
          className="mb-2 flex flex-wrap items-center gap-2 text-sm"
          aria-label={t("timeseriesEdit.grid.rowsLabel")}
        >
          <button
            onClick={() => setPage(currentPage - 1)}
            disabled={currentPage === 0}
          >
            {t("timeseriesEdit.grid.previousPage")}
          </button>
          <span aria-live="polite">
            {t("timeseriesEdit.grid.pageStatus", {
              page: currentPage + 1,
              pages: pageCount,
              from: pageStart + 1,
              to: pageStart + pageRows.length,
              total: displayRows.length,
            })}
          </span>
          <button
            onClick={() => setPage(currentPage + 1)}
            disabled={currentPage >= pageCount - 1}
          >
            {t("timeseriesEdit.grid.nextPage")}
          </button>
        </nav>
      )}
      <div style={{ marginBottom: "0.5rem" }}>
        <button
          onClick={() => {
            const trimmedTicker = ticker.trim().toUpperCase();
            const defaultTicker =
              trimmedTicker && exchange
                ? trimmedTicker.includes(".")
                  ? trimmedTicker
                  : `${trimmedTicker}.${exchange}`
                : trimmedTicker;
            // Undated rows sort last in either direction; jump to the last
            // page (clamped on render) so the new row is visible.
            setPage(Number.MAX_SAFE_INTEGER);
            setRows((rs) => [
              ...rs,
              {
                Date: "",
                Open: null,
                High: null,
                Low: null,
                Close: null,
                Volume: null,
                Ticker: defaultTicker,
                Source: "Manual",
              },
            ]);
          }}
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
