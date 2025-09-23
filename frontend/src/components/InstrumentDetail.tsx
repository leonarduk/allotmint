import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getInstrumentDetail, getInstrumentIntraday } from "../api";
import { money, percent } from "../lib/money";
import { translateInstrumentType } from "../lib/instrumentType";
import tableStyles from "../styles/table.module.css";
import i18n from "../i18n";
import { formatDateISO } from "../lib/date";
import { useConfig } from "../ConfigContext";
import type { InstrumentPosition, TradingSignal } from "../types";
import { RelativeViewToggle } from "./RelativeViewToggle";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";

type Variant = "drawer" | "standalone";

type Props = {
  ticker: string;
  name: string;
  currency?: string;
  instrument_type?: string | null;
  signal?: TradingSignal;
  onClose?: () => void;
  variant?: Variant;
  hidePositions?: boolean;
};

type Price = {
  date: string;
  close_gbp: number | null | undefined;
  close?: number | null | undefined;
};

type Position = InstrumentPosition & {
  market_value_gbp?: number | null | undefined;
  unrealised_gain_gbp?: number | null | undefined;
  gain_pct?: number | null | undefined;
};

type PositionsTableProps = {
  positions: Position[];
  loading: boolean;
  positiveColor?: string;
  negativeColor?: string;
  linkColor?: string;
  mutedColor?: string;
};

// ───────────────── helpers ─────────────────
const toNum = (v: unknown): number =>
  typeof v === "number" && Number.isFinite(v) ? v : NaN;

const fixed = (v: unknown, dp = 2): string => {
  const n = toNum(v);
  return Number.isFinite(n)
    ? new Intl.NumberFormat(i18n.language, {
        minimumFractionDigits: dp,
        maximumFractionDigits: dp,
      }).format(n)
    : "—";
};

export function InstrumentPositionsTable({
  positions,
  loading,
  positiveColor = "lightgreen",
  negativeColor = "red",
  linkColor = "#00d8ff",
  mutedColor = "#888",
}: PositionsTableProps) {
  const { t } = useTranslation();
  const { baseCurrency, relativeViewEnabled } = useConfig();

  return (
    <table
      className={tableStyles.table}
      style={{ fontSize: "0.85rem", marginBottom: "1rem" }}
    >
      <thead>
        <tr>
          <th className={tableStyles.cell}>{t("instrumentDetail.columns.account")}</th>
          {!relativeViewEnabled && (
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>
              {t("instrumentDetail.columns.units")}
            </th>
          )}
          {!relativeViewEnabled && (
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>
              {t("instrumentDetail.columns.market")}
            </th>
          )}
          {!relativeViewEnabled && (
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>
              {t("instrumentDetail.columns.gain")}
            </th>
          )}
          <th className={`${tableStyles.cell} ${tableStyles.right}`}>
            {t("instrumentDetail.columns.gainPct")}
          </th>
        </tr>
      </thead>
      <tbody>
        {loading ? (
          <tr>
            <td
              colSpan={relativeViewEnabled ? 2 : 5}
              className={`${tableStyles.cell} ${tableStyles.center}`}
              style={{ color: mutedColor }}
            >
              {t("app.loading")}
            </td>
          </tr>
        ) : positions.length ? (
          positions.map((pos, i) => (
            <tr key={`${pos.owner}-${pos.account}-${i}`}>
              <td className={tableStyles.cell}>
                <Link
                  to={`/portfolio/${encodeURIComponent(pos.owner ?? "")}`}
                  style={{ color: linkColor, textDecoration: "none" }}
                >
                  {pos.owner} – {pos.account}
                </Link>
              </td>
              {!relativeViewEnabled && (
                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                  {fixed(pos.units, 4)}
                </td>
              )}
              {!relativeViewEnabled && (
                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                  {money(pos.market_value_gbp, baseCurrency)}
                </td>
              )}
              {!relativeViewEnabled && (
                <td
                  className={`${tableStyles.cell} ${tableStyles.right}`}
                  style={{
                    color: toNum(pos.unrealised_gain_gbp) >= 0
                      ? positiveColor
                      : negativeColor,
                  }}
                >
                  {money(pos.unrealised_gain_gbp, baseCurrency)}
                </td>
              )}
              <td
                className={`${tableStyles.cell} ${tableStyles.right}`}
                style={{
                  color: toNum(pos.gain_pct) >= 0 ? positiveColor : negativeColor,
                }}
              >
                {percent(pos.gain_pct, 1)}
              </td>
            </tr>
          ))
        ) : (
          <tr>
            <td
              colSpan={relativeViewEnabled ? 2 : 5}
              className={`${tableStyles.cell} ${tableStyles.center}`}
              style={{ color: mutedColor }}
            >
              {t("instrumentDetail.noPositions")}
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

export function InstrumentDetail({
  ticker,
  name,
  currency: currencyProp,
  instrument_type, // ← comes from props now
  signal,
  onClose,
  variant = "drawer",
  hidePositions = false,
}: Props) {
  const { t } = useTranslation();
  const { baseCurrency } = useConfig();
  const palette = useMemo(
    () => ({
      background: variant === "drawer" ? "#111" : "transparent",
      text: variant === "drawer" ? "#eee" : "inherit",
      muted: variant === "drawer" ? "#aaa" : "#555",
      link: variant === "drawer" ? "#00d8ff" : "#1a73e8",
      positive: variant === "drawer" ? "lightgreen" : "#137333",
      negative: variant === "drawer" ? "red" : "#b3261e",
      accentBorder: variant === "drawer" ? "#222" : "#ddd",
    }),
    [variant],
  );
  const containerStyle = useMemo(
    () =>
      variant === "drawer"
        ? {
            position: "fixed" as const,
            top: 0,
            right: 0,
            bottom: 0,
            width: "420px",
            background: palette.background,
            color: palette.text,
            padding: "1rem",
            overflowY: "auto" as const,
            boxShadow: "-4px 0 8px rgba(0,0,0,0.5)",
          }
        : {
            position: "relative" as const,
            width: "100%",
            maxWidth: "100%",
            background: palette.background,
            color: palette.text === "inherit" ? undefined : palette.text,
            padding: 0,
          },
    [palette.background, palette.text, variant],
  );
  const [data, setData] = useState<{
    prices: Price[];
    positions: Position[];
    currency?: string | null;
  } | null>(null);

  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [currencyFromData, setCurrencyFromData] = useState<string | null>(null);
  const [showBollinger, setShowBollinger] = useState(false);
  const [showMA20, setShowMA20] = useState(false);
  const [showMA50, setShowMA50] = useState(false);
  const [showMA200, setShowMA200] = useState(false);
  const [showRSI, setShowRSI] = useState(false);
  const [days, setDays] = useState<number>(365);
  const [priceMode, setPriceMode] = useState<"close" | "intraday">("close");
  const [intradayPrices, setIntradayPrices] = useState<{ timestamp: string; close: number }[]>([]);
  const [intradayLoading, setIntradayLoading] = useState(false);
  const [intradayError, setIntradayError] = useState<string | null>(null);
  const [intradaySupported, setIntradaySupported] = useState(true);

  useEffect(() => {
    setLoading(true);
    setData(null);
    setErr(null);
    setCurrencyFromData(null);
    getInstrumentDetail(ticker, days)
      .then((d) => {
        const detail = d as {
          prices: Price[];
          positions: Position[];
          currency?: string | null;
        };
        setData(detail);
        setCurrencyFromData(detail.currency ?? null);
      })
      .catch((e: Error) => setErr(e.message))
      .finally(() => setLoading(false));
  }, [ticker, days]);

  useEffect(() => {
    setPriceMode("close");
    setIntradayPrices([]);
    setIntradaySupported(true);
    setIntradayError(null);
  }, [ticker]);

  useEffect(() => {
    if (priceMode !== "intraday") return;
    let active = true;
    setIntradayLoading(true);
    setIntradayError(null);
    getInstrumentIntraday(ticker)
      .then((res) => {
        if (!active) return;
        if (!res.prices?.length) {
          throw new Error("no data");
        }
        setIntradayPrices(res.prices);
      })
      .catch((e: Error) => {
        if (!active) return;
        setIntradayError(e.message);
        setIntradaySupported(false);
        setPriceMode("close");
      })
      .finally(() => {
        if (active) setIntradayLoading(false);
      });
    return () => {
      active = false;
    };
  }, [ticker, priceMode]);

  const displayCurrency = currencyFromData ?? currencyProp ?? "?";

  const [tickerBase, exch = "L"] = ticker.split(".", 2);
  const editLink = `/timeseries?ticker=${encodeURIComponent(tickerBase)}&exchange=${encodeURIComponent(exch)}`;

  const rawPrices = (data?.prices ?? [])
    .map((p) => ({ date: p.date, close_gbp: toNum(p.close_gbp ?? p.close) }))
    .filter((p) => Number.isFinite(p.close_gbp));

  const withChanges = rawPrices.map((p, i) => {
    const prev = rawPrices[i - 1];
    const change_gbp = prev ? p.close_gbp - prev.close_gbp : NaN;
    const change_pct = prev ? (change_gbp / prev.close_gbp) * 100 : NaN;
    return { ...p, change_gbp, change_pct };
  });

  const prices = withChanges.map((p, i, arr) => {
    const slice20 = arr.slice(Math.max(0, i - 19), i + 1);
    const mean20 =
      slice20.reduce((sum, s) => sum + s.close_gbp, 0) / slice20.length;
    const variance =
      slice20.reduce((sum, s) => Math.pow(s.close_gbp - mean20, 2) + sum, 0) /
      slice20.length;
    const stdDev = Math.sqrt(variance);
    const has20 = slice20.length === 20;

    const slice50 = arr.slice(Math.max(0, i - 49), i + 1);
    const mean50 =
      slice50.reduce((sum, s) => sum + s.close_gbp, 0) / slice50.length;
    const has50 = slice50.length === 50;

    const slice200 = arr.slice(Math.max(0, i - 199), i + 1);
    const mean200 =
      slice200.reduce((sum, s) => sum + s.close_gbp, 0) / slice200.length;
    const has200 = slice200.length === 200;

    const rsiSlice = arr.slice(Math.max(0, i - 14), i + 1);
    let rsi = NaN;
    if (rsiSlice.length === 15) {
      let gains = 0;
      let losses = 0;
      for (let j = 1; j < rsiSlice.length; j++) {
        const diff = rsiSlice[j].close_gbp - rsiSlice[j - 1].close_gbp;
        if (diff >= 0) gains += diff;
        else losses -= diff;
      }
      const avgGain = gains / 14;
      const avgLoss = losses / 14;
      if (avgLoss === 0) rsi = 100;
      else if (avgGain === 0) rsi = 0;
      else {
        const rs = avgGain / avgLoss;
        rsi = 100 - 100 / (1 + rs);
      }
    }

    return {
      ...p,
      bb_mid: has20 ? mean20 : NaN,
      bb_upper: has20 ? mean20 + 2 * stdDev : NaN,
      bb_lower: has20 ? mean20 - 2 * stdDev : NaN,
      ma20: has20 ? mean20 : NaN,
      ma50: has50 ? mean50 : NaN,
      ma200: has200 ? mean200 : NaN,
      rsi,
    };
  });

  // 7d / 30d change calculations
  const latestClose = rawPrices[rawPrices.length - 1]?.close_gbp ?? NaN;

  const lookup = (days: number): number => {
    if (!rawPrices.length) return NaN;
    const target = new Date(rawPrices[rawPrices.length - 1].date);
    target.setDate(target.getDate() - days);
    for (let i = rawPrices.length - 1; i >= 0; i--) {
      const d = new Date(rawPrices[i].date);
      if (d <= target) return rawPrices[i].close_gbp;
    }
    return NaN;
  };

  const close7 = lookup(7);
  const close30 = lookup(30);
  const change7dPct =
    Number.isFinite(latestClose) && Number.isFinite(close7)
      ? ((latestClose / close7 - 1) * 100)
      : NaN;
  const change30dPct =
    Number.isFinite(latestClose) && Number.isFinite(close30)
      ? ((latestClose / close30 - 1) * 100)
      : NaN;

  const positions = data?.positions ?? [];

  return (
    <div style={containerStyle}>
      {onClose && variant === "drawer" && (
        <button onClick={onClose} style={{ float: "right" }}>
          ✕
        </button>
      )}
      {signal && (
        <div style={{ marginBottom: "0.5rem" }}>
          <strong>{signal.action.toUpperCase()}</strong> – {signal.reason}
          {signal.confidence != null && (
            <div>Confidence: {(signal.confidence * 100).toFixed(0)}%</div>
          )}
          {signal.rationale && <div>{signal.rationale}</div>}
        </div>
      )}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "0.2rem",
        }}
      >
        <h2 style={{ marginBottom: 0 }}>{name}</h2>
        <RelativeViewToggle />
      </div>
      <div style={{ fontSize: "0.85rem", color: palette.muted }}>
        {ticker} • {displayCurrency} • {translateInstrumentType(t, instrument_type)} • {" "}
        <Link to={editLink} style={{ color: palette.link, textDecoration: "none" }}>
          {t("instrumentDetail.edit")}
        </Link>
      </div>
      <div style={{ fontSize: "0.85rem", marginBottom: "1rem" }}>
        <span
          style={{
            color: Number.isFinite(change7dPct)
              ? change7dPct >= 0
                ? palette.positive
                : palette.negative
              : undefined,
          }}
        >
          {t("instrumentDetail.change7d")} {loading ? t("app.loading") : percent(change7dPct, 1)}
        </span>
        {" • "}
        <span
          style={{
            color: Number.isFinite(change30dPct)
              ? change30dPct >= 0
                ? palette.positive
                : palette.negative
              : undefined,
          }}
        >
          {t("instrumentDetail.change30d")} {loading ? t("app.loading") : percent(change30dPct, 1)}
        </span>
      </div>
      {err && <p style={{ color: palette.negative }}>{err}</p>}

      {/* Chart */}
      <div style={{ marginBottom: "0.5rem" }}>
        <label style={{ fontSize: "0.85rem", marginRight: "1rem" }}>
          {t("instrumentDetail.range")}
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            style={{ marginLeft: "0.25rem" }}
            disabled={priceMode === "intraday"}
          >
            <option value={7}>{t("instrumentDetail.rangeOptions.1w")}</option>
            <option value={30}>{t("instrumentDetail.rangeOptions.1m")}</option>
            <option value={365}>{t("instrumentDetail.rangeOptions.1y")}</option>
            <option value={3650}>{t("instrumentDetail.rangeOptions.10y")}</option>
            <option value={0}>{t("instrumentDetail.rangeOptions.max")}</option>
          </select>
        </label>
        {priceMode === "close" && (
          <>
            <label style={{ fontSize: "0.85rem" }}>
              <input
                type="checkbox"
                checked={showBollinger}
                onChange={(e) => setShowBollinger(e.target.checked)}
              />{" "}
              {t("instrumentDetail.bollingerBands")}
            </label>
            <label style={{ fontSize: "0.85rem", marginLeft: "0.5rem" }}>
              <input
                type="checkbox"
                checked={showMA20}
                onChange={(e) => setShowMA20(e.target.checked)}
              />{" "}
              {t("instrumentDetail.ma20")}
            </label>
            <label style={{ fontSize: "0.85rem", marginLeft: "0.5rem" }}>
              <input
                type="checkbox"
                checked={showMA50}
                onChange={(e) => setShowMA50(e.target.checked)}
              />{" "}
              {t("instrumentDetail.ma50")}
            </label>
            <label style={{ fontSize: "0.85rem", marginLeft: "0.5rem" }}>
              <input
                type="checkbox"
                checked={showMA200}
                onChange={(e) => setShowMA200(e.target.checked)}
              />{" "}
              {t("instrumentDetail.ma200")}
            </label>
            <label style={{ fontSize: "0.85rem", marginLeft: "0.5rem" }}>
              <input
                type="checkbox"
                checked={showRSI}
                onChange={(e) => setShowRSI(e.target.checked)}
              />{" "}
              {t("instrumentDetail.rsi")}
            </label>
          </>
        )}
        <label style={{ fontSize: "0.85rem", marginLeft: "0.5rem" }}>
          <input
            type="checkbox"
            checked={priceMode === "intraday"}
            onChange={(e) =>
              setPriceMode(e.target.checked ? "intraday" : "close")
            }
            disabled={!intradaySupported}
          />{" "}
          {t("instrumentDetail.intraday")}
        </label>
      </div>
      {intradayError && (
        <div style={{ color: palette.negative, marginBottom: "0.5rem" }}>
          {t("instrumentDetail.intradayUnavailable")}
        </div>
      )}
      {priceMode === "intraday" ? (
        intradayLoading ? (
          <div
            style={{
              height: 220,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            {t("app.loading")}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={intradayPrices}>
              <XAxis dataKey="timestamp" hide />
              <YAxis domain={["auto", "auto"]} />
              <Tooltip
                wrapperStyle={{ color: "#000" }}
                labelStyle={{ color: "#000" }}
              />
              <Line type="monotone" dataKey="close" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )
      ) : loading ? (
        <div
          style={{
            height: 220,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {t("app.loading")}
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={prices}>
            <XAxis dataKey="date" hide />
            <YAxis yAxisId="price" domain={["auto", "auto"]} />
            {showRSI && (
              <YAxis yAxisId="rsi" domain={[0, 100]} orientation="right" />
            )}
            <Tooltip
              wrapperStyle={{ color: "#000" }}
              labelStyle={{ color: "#000" }}
            />
            {showBollinger && (
              <>
                <Line
                  type="monotone"
                  dataKey="bb_upper"
                  stroke="#8884d8"
                  dot={false}
                  strokeDasharray="3 3"
                  yAxisId="price"
                />
                <Line
                  type="monotone"
                  dataKey="bb_mid"
                  stroke="#ff7300"
                  dot={false}
                  strokeDasharray="5 5"
                  yAxisId="price"
                />
                <Line
                  type="monotone"
                  dataKey="bb_lower"
                  stroke="#8884d8"
                  dot={false}
                  strokeDasharray="3 3"
                  yAxisId="price"
                />
              </>
            )}
            {showMA20 && (
              <Line
                type="monotone"
                dataKey="ma20"
                stroke="#ff7300"
                dot={false}
                yAxisId="price"
              />
            )}
            {showMA50 && (
              <Line
                type="monotone"
                dataKey="ma50"
                stroke="#00bfff"
                dot={false}
                yAxisId="price"
              />
            )}
            {showMA200 && (
              <Line
                type="monotone"
                dataKey="ma200"
                stroke="#800080"
                dot={false}
                yAxisId="price"
              />
            )}
            {showRSI && (
              <Line
                type="monotone"
                dataKey="rsi"
                stroke="#ff0000"
                dot={false}
                yAxisId="rsi"
              />
            )}
            <Line type="monotone" dataKey="close_gbp" dot={false} yAxisId="price" />
          </LineChart>
        </ResponsiveContainer>
      )}

      {!hidePositions && (
        <>
          {/* Positions */}
          <h3 style={{ marginTop: "1.5rem" }}>{t("instrumentDetail.positions")}</h3>
          <InstrumentPositionsTable
            positions={positions}
            loading={loading}
            positiveColor={palette.positive}
            negativeColor={palette.negative}
            linkColor={palette.link}
            mutedColor={palette.muted}
          />
        </>
      )}

      {/* Recent Prices */}
      <h3>{t("instrumentDetail.recentPrices")}</h3>
      <table
        className={tableStyles.table}
        style={{ fontSize: "0.85rem", marginBottom: "1rem" }}
      >
        <thead>
          <tr>
            <th className={tableStyles.cell}>{t("instrumentDetail.priceColumns.date")}</th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>{t("instrumentDetail.priceColumns.close")}</th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>{t("instrumentDetail.priceColumns.delta")}</th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>{t("instrumentDetail.priceColumns.deltaPct")}</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td
                colSpan={4}
                className={`${tableStyles.cell} ${tableStyles.center}`}
                style={{ color: palette.muted }}
              >
                {t("app.loading")}
              </td>
            </tr>
          ) : prices.length ? (
            prices
              .slice(-60)
              .reverse()
              .map((p) => {
                const colour = Number.isFinite(p.change_gbp)
                  ? p.change_gbp >= 0
                    ? palette.positive
                    : palette.negative
                  : undefined;
                return (
                  <tr key={p.date}>
                    <td className={tableStyles.cell}>
                      {formatDateISO(new Date(p.date))}
                    </td>
                    <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                      {money(p.close_gbp, baseCurrency)}
                    </td>
                    <td
                      className={`${tableStyles.cell} ${tableStyles.right}`}
                      style={{ color: colour }}
                    >
                      {money(p.change_gbp, baseCurrency)}
                    </td>
                    <td
                      className={`${tableStyles.cell} ${tableStyles.right}`}
                      style={{ color: colour }}
                    >
                      {Number.isFinite(p.change_pct) ? (
                        <span
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            justifyContent: "flex-end",
                            gap: "0.25rem",
                            fontVariantNumeric: "tabular-nums",
                          }}
                        >
                          {p.change_pct >= 0 ? (
                            <ArrowUpRight size={12} />
                          ) : (
                            <ArrowDownRight size={12} />
                          )}
                          {percent(p.change_pct, 2)}
                        </span>
                      ) : (
                        percent(p.change_pct, 2)
                      )}
                    </td>
                  </tr>
                );
              })
          ) : (
            <tr>
              <td
                colSpan={4}
                className={`${tableStyles.cell} ${tableStyles.center}`}
                style={{ color: palette.muted }}
              >
                {t("instrumentDetail.noPriceData")}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
