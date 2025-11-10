import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  getPerformance,
  getAlphaVsBenchmark,
  getTrackingError,
  getMaxDrawdown,
} from "../api";
import type { PerformancePoint } from "../types";
import { percent, percentOrNa } from "../lib/money";
import { formatDateISO } from "../lib/date";
import type { DrawdownExtrema, DrawdownSeriesPoint } from "../types";

type Props = {
  owner: string | null;
  asOf?: string | null;
};

export function PerformanceDashboard({ owner, asOf }: Props) {
  const [data, setData] = useState<PerformancePoint[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [days, setDays] = useState<number>(365);
  const [alpha, setAlpha] = useState<number | null>(null);
  const [trackingError, setTrackingError] = useState<number | null>(null);
  const [maxDrawdown, setMaxDrawdown] = useState<number | null>(null);
  const [drawdownSeries, setDrawdownSeries] = useState<DrawdownSeriesPoint[]>([]);
  const [drawdownPeak, setDrawdownPeak] = useState<DrawdownExtrema | null>(null);
  const [drawdownTrough, setDrawdownTrough] = useState<DrawdownExtrema | null>(null);
  const [showDrawdownDetails, setShowDrawdownDetails] = useState(false);
  const [timeWeightedReturn, setTimeWeightedReturn] = useState<number | null>(
    null,
  );
  const [xirr, setXirr] = useState<number | null>(null);
  const [excludeCash, setExcludeCash] = useState<boolean>(false);
  const [reportingDate, setReportingDate] = useState<string | null>(null);
  const [previousDate, setPreviousDate] = useState<string | null>(null);
  const { t, i18n } = useTranslation();

  useEffect(() => {
    if (!owner) return;
    setErr(null);
    setData([]);
    setReportingDate(null);
    setPreviousDate(null);
    setDrawdownSeries([]);
    setDrawdownPeak(null);
    setDrawdownTrough(null);
    setShowDrawdownDetails(false);
    const reqDays = days === 0 ? 36500 : days;
    const opts = asOf ? { asOf } : undefined;
    Promise.all([
      getAlphaVsBenchmark(owner, "VWRL.L", reqDays, opts),
      getTrackingError(owner, "VWRL.L", reqDays, opts),
      getMaxDrawdown(owner, reqDays, opts),
      getPerformance(owner, reqDays, excludeCash, opts),
    ])
      .then(([alphaRes, teRes, mdRes, perf]) => {
        setData(perf.history);
        setAlpha(alphaRes.alpha_vs_benchmark);
        setTrackingError(teRes.tracking_error);
        setMaxDrawdown(mdRes.max_drawdown);
        setDrawdownSeries(mdRes.series ?? []);
        setDrawdownPeak(mdRes.peak ?? null);
        setDrawdownTrough(mdRes.trough ?? null);
        setTimeWeightedReturn(perf.time_weighted_return ?? null);
        setXirr(perf.xirr ?? null);
        setReportingDate(perf.reportingDate ?? null);
        setPreviousDate(perf.previousDate ?? null);
        const normalizedDrawdown =
          mdRes.max_drawdown != null && Math.abs(mdRes.max_drawdown) > 1
            ? mdRes.max_drawdown / 100
            : mdRes.max_drawdown;
        if (
          typeof normalizedDrawdown === "number" &&
          Math.abs(normalizedDrawdown) >= 0.9
        ) {
          setShowDrawdownDetails(true);
        }
      })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [owner, days, excludeCash, asOf]);

  if (!owner) return <p>{t("dashboard.selectMember")}</p>;
  if (err) return <p style={{ color: "red" }}>{err}</p>;
  if (!data.length) return <p>{t("common.loading")}</p>;

  const safeAlpha =
    alpha != null && Math.abs(alpha) > 1 ? alpha / 100 : alpha;
  const safeTrackingError =
    trackingError != null && Math.abs(trackingError) > 1
      ? trackingError / 100
      : trackingError;
  const safeMaxDrawdown =
    maxDrawdown != null && Math.abs(maxDrawdown) > 1
      ? maxDrawdown / 100
      : maxDrawdown;
  const safeTwr =
    timeWeightedReturn != null && Math.abs(timeWeightedReturn) > 1
      ? timeWeightedReturn / 100
      : timeWeightedReturn;
  const safeXirr =
    xirr != null && Math.abs(xirr) > 1 ? xirr / 100 : xirr;

  const formatSummaryDate = (value: string | null) => {
    if (!value) return "—";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return formatDateISO(parsed);
  };

  const formatDrawdownDate = (value: string | undefined | null) => {
    if (!value) return "—";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return formatDateISO(parsed);
  };

  const formatDrawdownNumber = (value: number | undefined | null) => {
    if (typeof value !== "number" || !Number.isFinite(value)) return "—";
    return new Intl.NumberFormat(i18n.language, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  };

  const normalizedDrawdown = safeMaxDrawdown;
  const drawdownPercentText =
    typeof normalizedDrawdown === "number"
      ? percent(normalizedDrawdown * 100, 2, i18n.language)
      : null;
  const severeDrawdown =
    typeof normalizedDrawdown === "number" &&
    Math.abs(normalizedDrawdown) >= 0.9;

  const drawdownRangeText =
    drawdownPeak && drawdownTrough
      ? t("dashboard.drawdownRangeWithValues", {
          start: formatDrawdownDate(drawdownPeak.date),
          end: formatDrawdownDate(drawdownTrough.date),
          startValue: formatDrawdownNumber(drawdownPeak.value),
          endValue: formatDrawdownNumber(drawdownTrough.value),
        })
      : t("dashboard.drawdownRangeUnknown");

  const diagnosticsHref = owner
    ? `/performance/${encodeURIComponent(owner)}/diagnostics`
    : "#";

  const drawdownDetailsAvailable = drawdownSeries.length > 0;

  return (
    <div style={{ marginTop: "1rem" }}>
      <div style={{ marginBottom: "0.5rem" }}>
        <label style={{ fontSize: "0.85rem" }}>
          {t("dashboard.range")}
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            style={{ marginLeft: "0.25rem" }}
          >
            <option value={7}>{t("dashboard.rangeOptions.1w")}</option>
            <option value={30}>{t("dashboard.rangeOptions.1m")}</option>
            <option value={365}>{t("dashboard.rangeOptions.1y")}</option>
            <option value={3650}>{t("dashboard.rangeOptions.10y")}</option>
            <option value={0}>{t("dashboard.rangeOptions.max")}</option>
          </select>
        </label>
        <label style={{ fontSize: "0.85rem", marginLeft: "1rem" }}>
          {t("dashboard.excludeCash")}
          <input
            type="checkbox"
            checked={excludeCash}
            onChange={(e) => setExcludeCash(e.target.checked)}
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
      </div>
      <div
        style={{
          display: "flex",
          gap: "1rem",
          flexWrap: "wrap",
          fontSize: "0.9rem",
          color: "#aaa",
          marginBottom: "0.75rem",
        }}
      >
        <div data-testid="reporting-date-summary">
          <span style={{ fontWeight: 600 }}>
            {t("dashboard.reportingDate")}:
          </span>{" "}
          {formatSummaryDate(reportingDate)}
        </div>
        <div data-testid="previous-date-summary">
          <span style={{ fontWeight: 600 }}>
            {t("dashboard.previousDate")}:
          </span>{" "}
          {formatSummaryDate(previousDate)}
        </div>
      </div>
      <div
        style={{
          display: "flex",
          gap: "1rem",
          marginBottom: "1rem",
        }}
      >
        <div>
          <div style={{ fontSize: "0.9rem", color: "#aaa" }}>{t("dashboard.alphaVsBenchmark")}</div>
          <div style={{ fontSize: "1.1rem", fontWeight: "bold" }}>
            {percentOrNa(safeAlpha)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: "0.9rem", color: "#aaa" }}>{t("dashboard.trackingError")}</div>
          <div style={{ fontSize: "1.1rem", fontWeight: "bold" }}>
            {percentOrNa(safeTrackingError)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: "0.9rem", color: "#aaa" }}>{t("dashboard.maxDrawdown")}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
            <span style={{ fontSize: "1.1rem", fontWeight: "bold" }}>
              {percentOrNa(safeMaxDrawdown)}
            </span>
            {drawdownDetailsAvailable && (
              <button
                type="button"
                onClick={() => setShowDrawdownDetails((prev) => !prev)}
                style={{
                  alignSelf: "flex-start",
                  fontSize: "0.8rem",
                  color: "#60a5fa",
                  background: "transparent",
                  border: "none",
                  padding: 0,
                  cursor: "pointer",
                  textDecoration: "underline",
                }}
              >
                {showDrawdownDetails
                  ? t("dashboard.maxDrawdownHide")
                  : t("dashboard.maxDrawdownExplain")}
              </button>
            )}
          </div>
        </div>
        <div>
          <div style={{ fontSize: "0.9rem", color: "#aaa" }}>{t("dashboard.timeWeightedReturn")}</div>
          <div style={{ fontSize: "1.1rem", fontWeight: "bold" }}>
            {percentOrNa(safeTwr)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: "0.9rem", color: "#aaa" }}>{t("dashboard.xirr")}</div>
          <div style={{ fontSize: "1.1rem", fontWeight: "bold" }}>
            {percentOrNa(safeXirr)}
          </div>
        </div>
      </div>
      {showDrawdownDetails && (
        <div
          style={{
            marginBottom: "1.5rem",
            border: "1px solid #374151",
            background: "rgba(17, 24, 39, 0.6)",
            borderRadius: "0.75rem",
            padding: "1rem",
          }}
        >
          <h3
            style={{
              marginTop: 0,
              marginBottom: "0.5rem",
              fontSize: "1rem",
              fontWeight: 600,
              color: "#f9fafb",
            }}
          >
            {t("dashboard.maxDrawdownDetailsHeading")}
          </h3>
          <p style={{ fontSize: "0.85rem", color: "#d1d5db", marginBottom: "0.5rem" }}>
            {drawdownRangeText}
          </p>
          {drawdownPercentText && (
            <p style={{ fontSize: "0.85rem", color: "#d1d5db", marginBottom: "0.5rem" }}>
              {t("dashboard.drawdownPercentSummary", {
                drawdown: drawdownPercentText,
              })}
            </p>
          )}
          {severeDrawdown && (
            <p style={{ fontSize: "0.85rem", color: "#facc15", marginBottom: "0.75rem" }}>
              {t("dashboard.drawdownSuspicious")}
            </p>
          )}
          {drawdownDetailsAvailable ? (
            <div style={{ height: 220 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={drawdownSeries}>
                  <XAxis dataKey="date" />
                  <YAxis
                    tickFormatter={(v) => percent(v * 100, 1, i18n.language)}
                  />
                  <Tooltip
                    formatter={(value: number) =>
                      percent(value * 100, 2, i18n.language)
                    }
                  />
                  {drawdownPeak && drawdownTrough && (
                    <ReferenceArea
                      x1={drawdownPeak.date}
                      x2={drawdownTrough.date}
                      fill="rgba(239,68,68,0.1)"
                      strokeOpacity={0}
                    />
                  )}
                  <Line
                    type="monotone"
                    dataKey="drawdown"
                    stroke="#f97316"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p style={{ fontSize: "0.85rem", color: "#9ca3af", marginBottom: 0 }}>
              {t("dashboard.drawdownSeriesUnavailable")}
            </p>
          )}
          <p style={{ fontSize: "0.75rem", color: "#9ca3af", marginTop: "0.75rem" }}>
            {t("dashboard.drawdownChartDescription")}
          </p>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "0.75rem",
              marginTop: "0.75rem",
            }}
          >
            {owner && (
              <Link
                to={diagnosticsHref}
                style={{
                  display: "inline-block",
                  padding: "0.5rem 0.85rem",
                  borderRadius: "0.5rem",
                  backgroundColor: "#2563eb",
                  color: "#fff",
                  textDecoration: "none",
                  fontSize: "0.85rem",
                }}
              >
                {t("dashboard.openDiagnostics")}
              </Link>
            )}
            <Link
              to="/metrics-explained#max-drawdown"
              style={{
                alignSelf: "center",
                fontSize: "0.85rem",
                color: "#60a5fa",
              }}
            >
              {t("dashboard.viewMetricsExplanation")}
            </Link>
          </div>
        </div>
      )}
      <h2>{t("dashboard.portfolioValue")}</h2>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data}>
          <XAxis dataKey="date" />
          <YAxis />
          <Tooltip />
          <Line type="monotone" dataKey="value" stroke="#8884d8" dot={false} />
        </LineChart>
      </ResponsiveContainer>

      <h2 style={{ marginTop: "2rem" }}>{t("dashboard.cumulativeReturn")}</h2>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data}>
          <XAxis dataKey="date" />
          <YAxis tickFormatter={(v) => percent(v * 100, 2, i18n.language)} />
          <Tooltip formatter={(v: number) => percent(v * 100, 2, i18n.language)} />
          <Line
            type="monotone"
            dataKey="cumulative_return"
            stroke="#82ca9d"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
      {owner && (
        <div style={{ marginTop: "1rem" }}>
          <Link
            to={diagnosticsHref}
            style={{
              display: "inline-block",
              padding: "0.5rem 0.85rem",
              borderRadius: "0.5rem",
              backgroundColor: "#2563eb",
              color: "#fff",
              textDecoration: "none",
            }}
          >
            {t("dashboard.openDiagnostics")}
          </Link>
        </div>
      )}
    </div>
  );
}

export default PerformanceDashboard;
