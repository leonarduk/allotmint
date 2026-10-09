import { useEffect, useId, useMemo, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  ReferenceLine,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts";
import { getInstrumentDetail, searchInstruments } from "../api";
import ChartSkeleton from "./skeletons/ChartSkeleton";
import {
  COMPARE_COLORS,
  MAX_COMPARE_SERIES,
  buildCompareRows,
  compareKey,
  type CompareSeries,
} from "./instrumentCompare";

type Props = {
  /** The instrument the page is about; always the first series. */
  ticker: string;
  days: number;
  /** The base instrument's closes, already loaded by the parent chart. */
  basePoints: CompareSeries["points"];
  /** Extra tickers to overlay; owned by the parent so it can swap charts. */
  tickers: string[];
  onTickersChange: (tickers: string[]) => void;
  errorColor: string;
};

type Loaded = { points: CompareSeries["points"] } | { error: string };

type RawPrice = {
  date: string;
  close?: number | null;
  close_gbp?: number | null;
};

/**
 * Native close where present, else the reporting-currency close.  Either is
 * fine for a % change chart; the native one avoids FX moves leaking in.
 */
const toPoints = (prices: RawPrice[] | undefined): CompareSeries["points"] =>
  (prices ?? [])
    .map((p) => ({ date: p.date, close: Number(p.close ?? p.close_gbp) }))
    .filter((p) => Number.isFinite(p.close));

const formatPct = (value: unknown) =>
  typeof value === "number" && Number.isFinite(value)
    ? `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`
    : "—";

/** Suggest tickers as the user types, via the existing instrument search. */
function useTickerSuggestions(query: string) {
  const [suggestions, setSuggestions] = useState<
    { ticker: string; name: string }[]
  >([]);
  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setSuggestions([]);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      searchInstruments(trimmed, undefined, undefined, controller.signal)
        .then(setSuggestions)
        .catch(() => {
          // Suggestions are a convenience; a typed ticker can still be added.
          if (!controller.signal.aborted) setSuggestions([]);
        });
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query]);
  return suggestions;
}

/**
 * Fetch each compared ticker's history for the selected range.  Results are
 * keyed by range too, so changing the range refetches rather than reusing.
 */
function useCompareHistories(tickers: string[], days: number) {
  const [cache, setCache] = useState<Record<string, Loaded>>({});
  useEffect(() => {
    const controller = new AbortController();
    for (const tk of tickers) {
      const key = `${days}:${tk}`;
      if (cache[key]) continue;
      getInstrumentDetail(tk, days, controller.signal)
        .then((d) => {
          const points = toPoints((d as { prices?: RawPrice[] }).prices);
          setCache((prev) => ({
            ...prev,
            [key]: points.length ? { points } : { error: "no data" },
          }));
        })
        .catch((e: Error) => {
          if (controller.signal.aborted) return;
          setCache((prev) => ({ ...prev, [key]: { error: e.message } }));
        });
    }
    return () => controller.abort();
    // `cache` is deliberately omitted: it only skips tickers already in hand,
    // and re-running on every arrival would abort the requests still in flight.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tickers, days]);
  return useMemo(
    () =>
      Object.fromEntries(
        tickers.flatMap((tk) => {
          const hit = cache[`${days}:${tk}`];
          return hit ? [[tk, hit]] : [];
        }),
      ) as Record<string, Loaded>,
    [cache, tickers, days],
  );
}

export function CompareSeriesPanel({
  ticker,
  days,
  basePoints,
  tickers,
  onTickersChange,
  errorColor,
}: Props) {
  const { t } = useTranslation();
  const listId = useId();
  const [query, setQuery] = useState("");
  const suggestions = useTickerSuggestions(query);
  const loaded = useCompareHistories(tickers, days);

  const addTicker = (event: FormEvent) => {
    event.preventDefault();
    const next = query.trim().toUpperCase();
    setQuery("");
    if (!next || next === ticker.toUpperCase() || tickers.includes(next))
      return;
    onTickersChange([...tickers, next]);
  };

  const pending = tickers.some((tk) => !loaded[tk]);
  // Colours follow the ticker's slot, not its position among loaded series,
  // so a failed or slow ticker never shifts the others' colours.
  const series = useMemo(
    () =>
      [
        { ticker, points: basePoints, color: COMPARE_COLORS[0] },
        ...tickers.map((tk, i) => {
          const hit = loaded[tk];
          return {
            ticker: tk,
            points: hit && "points" in hit ? hit.points : [],
            color: COMPARE_COLORS[(i + 1) % COMPARE_COLORS.length],
          };
        }),
      ].filter((s) => s.points.length > 0),
    [ticker, basePoints, loaded, tickers],
  );
  const rows = useMemo(() => buildCompareRows(series), [series]);
  const atLimit = tickers.length + 1 >= MAX_COMPARE_SERIES;

  return (
    <div style={{ marginBottom: "0.5rem" }}>
      <form
        onSubmit={addTicker}
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.5rem",
          alignItems: "center",
        }}
      >
        <label style={{ fontSize: "0.85rem" }}>
          {t("instrumentDetail.compare.label")}{" "}
          <input
            type="text"
            list={listId}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("instrumentDetail.compare.placeholder")}
            disabled={atLimit}
            style={{ width: "10rem" }}
          />
        </label>
        <datalist id={listId}>
          {suggestions.map((s) => (
            <option key={s.ticker} value={s.ticker}>
              {s.name}
            </option>
          ))}
        </datalist>
        <button type="submit" disabled={atLimit || !query.trim()}>
          {t("instrumentDetail.compare.add")}
        </button>
        {tickers.map((tk, i) => {
          const failed = "error" in (loaded[tk] ?? {});
          return (
            <span
              key={tk}
              style={{
                fontSize: "0.8rem",
                border: `1px solid ${COMPARE_COLORS[(i + 1) % COMPARE_COLORS.length]}`,
                borderRadius: "1rem",
                padding: "0 0.5rem",
                color: failed ? errorColor : undefined,
              }}
              title={
                failed ? t("instrumentDetail.compare.loadFailed") : undefined
              }
            >
              {tk}
              {failed && " ⚠"}{" "}
              <button
                type="button"
                aria-label={t("instrumentDetail.compare.remove", {
                  ticker: tk,
                })}
                onClick={() => onTickersChange(tickers.filter((x) => x !== tk))}
                style={{
                  border: "none",
                  background: "none",
                  cursor: "pointer",
                  padding: 0,
                }}
              >
                ×
              </button>
            </span>
          );
        })}
        {tickers.length > 0 && (
          <button type="button" onClick={() => onTickersChange([])}>
            {t("instrumentDetail.compare.clear")}
          </button>
        )}
      </form>
      {tickers.length > 0 &&
        (pending && rows.length === 0 ? (
          <ChartSkeleton height={260} label={t("app.loading")} />
        ) : (
          <>
            <div style={{ fontSize: "0.8rem", margin: "0.25rem 0" }}>
              {t("instrumentDetail.compare.rebasedNote")}
            </div>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={rows}>
                <XAxis dataKey="date" hide />
                <YAxis
                  domain={["auto", "auto"]}
                  tickFormatter={(v: number) => `${Math.round(v)}%`}
                />
                <ReferenceLine y={0} stroke="#999" strokeDasharray="3 3" />
                <Tooltip
                  wrapperStyle={{ color: "#000" }}
                  labelStyle={{ color: "#000" }}
                  formatter={(value) => formatPct(value)}
                />
                <Legend />
                {series.map((s, i) => (
                  <Line
                    key={s.ticker}
                    type="monotone"
                    dataKey={compareKey(i)}
                    name={s.ticker}
                    stroke={s.color}
                    strokeWidth={i === 0 ? 2 : 1.5}
                    dot={false}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </>
        ))}
    </div>
  );
}
