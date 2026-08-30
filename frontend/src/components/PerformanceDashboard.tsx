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
  getGroupPerformance,
  getGroupAlphaVsBenchmark,
  getGroupTrackingError,
  getGroupMaxDrawdown,
} from "../api";
import type { PerformancePoint } from "../types";
import { percent, percentOrNa } from "../lib/money";
import { formatDateISO } from "../lib/date";
import type { DrawdownExtrema, DrawdownSeriesPoint } from "../types";
import InfoTip from "./InfoTip";

type Props = {
  owner: string | null;
  /**
   * Group slug (e.g. "all") to view combined household performance instead
   * of a single owner's. When set, `owner` is ignored and owner-only UI
   * (the diagnostics deep link) is hidden -- diagnostics stay owner-scoped
   * only (#7228).
   */
  group?: string | null;
  asOf?: string | null;
};

// The benchmark alpha/tracking-error are measured against. Named on screen
// (see #7230) because "Alpha vs Benchmark" is not interpretable without it.
const BENCHMARK_TICKER = "VWRL.L";

export function PerformanceDashboard({ owner, group, asOf }: Props) {
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
  const [partialMembers, setPartialMembers] = useState<string[]>([]);
  const { t, i18n } = useTranslation();

  const activeGroup = group || null;
  const activeOwner = activeGroup ? null : owner || null;

  useEffect(() => {
    if (!activeGroup && !activeOwner) return;
    setErr(null);
    setData([]);
    setReportingDate(null);
    setPreviousDate(null);
    setPartialMembers([]);
    setDrawdownSeries([]);
    setDrawdownPeak(null);
    setDrawdownTrough(null);
    setShowDrawdownDetails(false);
    const reqDays = days === 0 ? 36500 : days;
    const opts = asOf ? { asOf } : undefined;
    const fetches = activeGroup
      ? Promise.all([
          getGroupAlphaVsBenchmark(activeGroup, BENCHMARK_TICKER, reqDays),
          getGroupTrackingError(activeGroup, BENCHMARK_TICKER, reqDays),
          getGroupMaxDrawdown(activeGroup, reqDays),
          getGroupPerformance(activeGroup, reqDays, excludeCash, opts),
        ])
      : Promise.all([
          getAlphaVsBenchmark(activeOwner as string, BENCHMARK_TICKER, reqDays, opts),
          getTrackingError(activeOwner as string, BENCHMARK_TICKER, reqDays, opts),
          getMaxDrawdown(activeOwner as string, reqDays, opts),
          getPerformance(activeOwner as string, reqDays, excludeCash, opts),
        ]);
    fetches
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
        setPartialMembers(perf.partial ? perf.missingMembers ?? [] : []);
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
  }, [activeGroup, activeOwner, days, excludeCash, asOf]);

  if (!activeGroup && !activeOwner) return <p>{t("dashboard.selectMember")}</p>;
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

  const diagnosticsHref = activeOwner
    ? `/performance/${encodeURIComponent(activeOwner)}/diagnostics`
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
      {partialMembers.length > 0 && (
        <p
          data-testid="performance-partial-warning"
          style={{
            fontSize: "0.85rem",
            color: "#facc15",
            marginBottom: "0.75rem",
          }}
        >
          {t("dashboard.performancePartialMembers", {
            members: partialMembers.join(", "),
          })}
        </p>
      )}
      <div
        className="flex-wrap-row"
        style={{
          gap: "1rem",
          marginBottom: "1rem",
        }}
      >
        <div>
          <div style={{ fontSize: "0.9rem", color: "#aaa" }}>
            {t("dashboard.alphaVsBenchmark")}
            <InfoTip
              label={t("dashboard.alphaVsBenchmarkInfoLabel", "What does Alpha vs Benchmark mean?")}
              to="/metrics-explained#alpha-vs-benchmark"
            >
              {t(
                "dashboard.alphaVsBenchmarkInfo",
                "Alpha measures how much the portfolio's return differed from {{ticker}} over the selected period.",
                { ticker: BENCHMARK_TICKER },
              )}
            </InfoTip>
          </div>
          <div style={{ fontSize: "1.1rem", fontWeight: "bold" }}>
            {percentOrNa(safeAlpha)}
          </div>
          <div style={{ fontSize: "0.75rem", color: "#777" }}>
            {t("dashboard.vsBenchmark", "vs {{ticker}}", { ticker: BENCHMARK_TICKER })}
          </div>
        </div>
        <div>
          <div style={{ fontSize: "0.9rem", color: "#aaa" }}>
            {t("dashboard.trackingError")}
            <InfoTip
              label={t("dashboard.trackingErrorInfoLabel", "What does Tracking Error mean?")}
              to="/metrics-explained#tracking-error"
            >
              {t(
                "dashboard.trackingErrorInfo",
                "Tracking error measures how much the portfolio's daily returns varied from {{ticker}}'s, annualised.",
                { ticker: BENCHMARK_TICKER },
              )}
            </InfoTip>
          </div>
          <div style={{ fontSize: "1.1rem", fontWeight: "bold" }}>
            {percentOrNa(safeTrackingError)}
          </div>
          <div style={{ fontSize: "0.75rem", color: "#777" }}>
            {t("dashboard.vsBenchmark", "vs {{ticker}}", { ticker: BENCHMARK_TICKER })}
          </div>
        </div>
        <div>
          <div style={{ fontSize: "0.9rem", color: "#aaa" }}>
            {t("dashboard.maxDrawdown")}
            <InfoTip
              label={t("dashboard.maxDrawdownInfoLabel", "What does Max Drawdown mean?")}
              to="/metrics-explained#max-drawdown"
            >
              {t(
                "dashboard.maxDrawdownInfo",
                "Max drawdown is the largest peak-to-trough fall in portfolio value over the selected period.",
              )}
            </InfoTip>
          </div>
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
          <div style={{ fontSize: "0.9rem", color: "#aaa" }}>
            {t("dashboard.timeWeightedReturn")}
            <InfoTip
              label={t("dashboard.timeWeightedReturnInfoLabel", "What does Time-Weighted Return mean?")}
              to="/metrics-explained#time-weighted-return"
            >
              {t(
                "dashboard.timeWeightedReturnInfo",
                "Time-weighted return measures the portfolio's compounded growth rate, independent of the timing and size of deposits and withdrawals.",
              )}
            </InfoTip>
          </div>
          <div style={{ fontSize: "1.1rem", fontWeight: "bold" }}>
            {percentOrNa(safeTwr)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: "0.9rem", color: "#aaa" }}>
            {t("dashboard.xirr")}
            <InfoTip
              label={t("dashboard.xirrInfoLabel", "What does XIRR mean?")}
              to="/metrics-explained#xirr"
            >
              {t(
                "dashboard.xirrInfo",
                "XIRR is the annualised internal rate of return calculated from the portfolio's actual dated cash flows.",
              )}
            </InfoTip>
          </div>
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
              <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                <LineChart data={drawdownSeries}>
                  <XAxis dataKey="date" />
                  <YAxis
                    tickFormatter={(v) => percent(v * 100, 1, i18n.language)}
                  />
                  <Tooltip
                    formatter={(value) =>
                      percent(((value as number | undefined) ?? 0) * 100, 2, i18n.language)
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
            {activeOwner && (
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
          <Tooltip formatter={(v) => percent(((v as number | undefined) ?? 0) * 100, 2, i18n.language)} />
          <Line
            type="monotone"
            dataKey="cumulative_return"
            stroke="#82ca9d"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
      {activeOwner && (
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
