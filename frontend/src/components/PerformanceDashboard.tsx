import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  Legend,
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
import type { PerformancePoint, PortfolioReturnBasisFields } from "../types";
import { percent, wholeMoney } from "../lib/money";
import { paddedDomain } from "../lib/chartDomain";
import { useReportingCurrency } from "../hooks/useReportingCurrency";
import { formatDateISO } from "../lib/date";
import type { DrawdownExtrema, DrawdownSeriesPoint } from "../types";
import InfoTip from "./InfoTip";
import PortfolioFxAttribution from "./PortfolioFxAttribution";
import FractionMetric from "./FractionMetric";
import ReturnBasisNote from "./ReturnBasisNote";
import LoadingStatus from "./skeletons/LoadingStatus";
import PortfolioDashboardSkeleton from "./skeletons/PortfolioDashboardSkeleton";
import {
  buildCumulativeComparison,
  type CumulativeComparisonPoint,
} from "../lib/benchmarkSeries";
import {
  classifyDrawdown,
  DRAWDOWN_RANGE,
  drawdownNeedsAttention,
  RETURN_RANGE,
  TRACKING_ERROR_RANGE,
} from "../lib/metricPlausibility";

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
// Muted metric labels that still meet WCAG AA on both themes (#7824): the
// old #aaa/#777 greys were ~2.3:1 / ~4.5:1 on the light background.
const METRIC_LABEL_CLASS = "text-[var(--surface-muted-color)]";

// Distinct hue and dash so the benchmark never reads as the portfolio line (#7833).
const PORTFOLIO_LINE_COLOUR = "#82ca9d";
const BENCHMARK_LINE_COLOUR = "#f59e0b";

// "Open diagnostics" is developer surface, so it is a plain text link like
// the page's other secondary actions, never a primary button (#7214).
const SECONDARY_LINK_STYLE = {
  alignSelf: "center",
  fontSize: "0.85rem",
  color: "#60a5fa",
} as const;

// The four metric requests, settled independently so one failing never blanks
// the rest (#7228, #10083), and retried independently from the banner (#10755).
type MetricKey = "alpha" | "trackingError" | "maxDrawdown" | "performance";
const ALL_METRICS: MetricKey[] = ["alpha", "trackingError", "maxDrawdown", "performance"];
const METRIC_LABEL_KEYS: Record<MetricKey, string> = {
  alpha: "dashboard.alphaVsBenchmark",
  trackingError: "dashboard.trackingError",
  maxDrawdown: "dashboard.maxDrawdown",
  performance: "dashboard.portfolioValue",
};

// Metric units (fractions) and plausibility handling live in
// lib/metricPlausibility.ts and FractionMetric, shared with the group view
// (#8570).

export function PerformanceDashboard({ owner, group, asOf }: Props) {
  const reporting = useReportingCurrency();
  const [data, setData] = useState<PerformancePoint[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [days, setDays] = useState<number>(365);
  const [alpha, setAlpha] = useState<number | null>(null);
  const [comparison, setComparison] = useState<CumulativeComparisonPoint[]>([]);
  const [returnBasis, setReturnBasis] = useState<PortfolioReturnBasisFields | null>(null);
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
  // A metric endpoint failing must not blank the whole dashboard -- each of
  // the four performance-metric fetches below is settled independently so
  // the rest of the page still renders with the failed metric(s) shown as
  // unavailable rather than losing everything (DeepSeek review round 2,
  // #7228). The banner can retry just the failed ones (#10755): on a cold
  // backend cache the parallel set can pass the client timeout.
  const [failedMetrics, setFailedMetrics] = useState<MetricKey[]>([]);
  const [retrying, setRetrying] = useState(false);
  // Bumped whenever the scope changes or the component unmounts, so a load
  // or retry started for an earlier scope never writes into this one.
  const loadGeneration = useRef(0);
  // True once this load's fetches have settled. Gating "loading" on this,
  // not on `data.length`, keeps a successful-but-empty history from showing
  // "Loading..." forever (#7629).
  const [loaded, setLoaded] = useState<boolean>(false);
  const { t, i18n } = useTranslation();

  const activeGroup = group || null;
  const activeOwner = activeGroup ? null : owner || null;

  // Fetch ``metrics`` and apply each one that loads; resolves once all have
  // settled. ``isCurrent`` turns false once the scope has moved on, so stale
  // results (StrictMode's first run, a superseded range) are dropped.
  const loadMetrics = useCallback(
    (metrics: MetricKey[], isCurrent: () => boolean): Promise<void> => {
      const reqDays = days === 0 ? 36500 : days;
      const opts = asOf ? { asOf } : undefined;

      const settle = <T,>(
        key: MetricKey,
        request: () => Promise<T>,
        onLoaded: (value: T) => void,
      ): Promise<MetricKey | null> =>
        request().then(
          (value) => {
            if (isCurrent()) onLoaded(value);
            return null;
          },
          (reason: unknown) => {
            // Without this a failed metric left no diagnostic beyond the
            // generic banner (#7629).
            if (isCurrent()) console.error("Performance metric failed to load", reason);
            return key;
          },
        );

      // Group alpha/tracking error are computed by the backend from the
      // *combined* group portfolio series (see getGroupAlphaVsBenchmark /
      // getGroupTrackingError in api.ts), so they are meaningful aggregates --
      // not an average of each member's alpha -- and are rendered the same way
      // as the owner-scoped values. Owner scope is unchanged.
      const loaders: Record<MetricKey, () => Promise<MetricKey | null>> = {
        alpha: () =>
          settle(
            "alpha",
            () =>
              activeGroup
                ? getGroupAlphaVsBenchmark(activeGroup, BENCHMARK_TICKER, reqDays)
                : getAlphaVsBenchmark(activeOwner as string, BENCHMARK_TICKER, reqDays, opts),
            (res) => {
              setAlpha(res.alpha_vs_benchmark);
              setComparison(buildCumulativeComparison(res.series));
              setReturnBasis({
                portfolio_return_basis: res.portfolio_return_basis,
                portfolio_price_basis_share: res.portfolio_price_basis_share,
                portfolio_unpriced_holdings: res.portfolio_unpriced_holdings,
              });
            },
          ),
        trackingError: () =>
          settle(
            "trackingError",
            () =>
              activeGroup
                ? getGroupTrackingError(activeGroup, BENCHMARK_TICKER, reqDays)
                : getTrackingError(activeOwner as string, BENCHMARK_TICKER, reqDays, opts),
            (res) => setTrackingError(res.tracking_error),
          ),
        maxDrawdown: () =>
          settle(
            "maxDrawdown",
            () =>
              activeGroup
                ? getGroupMaxDrawdown(activeGroup, reqDays)
                : getMaxDrawdown(activeOwner as string, reqDays, opts),
            (mdRes) => {
              setMaxDrawdown(mdRes.max_drawdown);
              setDrawdownSeries(mdRes.series ?? []);
              setDrawdownPeak(mdRes.peak ?? null);
              setDrawdownTrough(mdRes.trough ?? null);
              // max_drawdown is a fraction; a severe (<= -90%) or implausible
              // value auto-expands the details so the user sees the warning.
              if (drawdownNeedsAttention(classifyDrawdown(mdRes.max_drawdown))) {
                setShowDrawdownDetails(true);
              }
            },
          ),
        performance: () =>
          settle(
            "performance",
            () =>
              activeGroup
                ? getGroupPerformance(activeGroup, reqDays, excludeCash, opts)
                : getPerformance(activeOwner as string, reqDays, excludeCash, opts),
            (perf) => {
              setData(perf.history);
              setTimeWeightedReturn(perf.time_weighted_return ?? null);
              setXirr(perf.xirr ?? null);
              setReportingDate(perf.reportingDate ?? null);
              setPreviousDate(perf.previousDate ?? null);
              setPartialMembers(perf.partial ? perf.missingMembers ?? [] : []);
            },
          ),
      };

      return Promise.all(metrics.map((key) => loaders[key]())).then((results) => {
        if (!isCurrent()) return;
        const failed = results.filter((key): key is MetricKey => key !== null);
        // Metrics not requested this time keep their previous state, so a
        // retry never forgets a failure it did not retry.
        setFailedMetrics((previous) =>
          ALL_METRICS.filter((key) =>
            metrics.includes(key) ? failed.includes(key) : previous.includes(key),
          ),
        );
      });
    },
    [activeGroup, activeOwner, days, excludeCash, asOf],
  );

  useEffect(() => {
    if (!activeGroup && !activeOwner) return;
    loadGeneration.current += 1;
    const generation = loadGeneration.current;
    const isCurrent = () => loadGeneration.current === generation;
    setErr(null);
    setData([]);
    setReportingDate(null);
    setPreviousDate(null);
    setPartialMembers([]);
    setDrawdownSeries([]);
    setDrawdownPeak(null);
    setDrawdownTrough(null);
    setShowDrawdownDetails(false);
    setAlpha(null);
    setComparison([]);
    setReturnBasis(null);
    setTrackingError(null);
    setMaxDrawdown(null);
    setTimeWeightedReturn(null);
    setXirr(null);
    setFailedMetrics([]);
    setRetrying(false);
    setLoaded(false);

    void loadMetrics(ALL_METRICS, isCurrent).then(() => {
      if (isCurrent()) setLoaded(true);
    });

    return () => {
      loadGeneration.current += 1;
    };
  }, [activeGroup, activeOwner, loadMetrics]);

  // Refetch only the metrics that failed, keeping the ones already shown (#10755).
  const retryFailedMetrics = () => {
    const generation = loadGeneration.current;
    const isCurrent = () => loadGeneration.current === generation;
    setRetrying(true);
    void loadMetrics(failedMetrics, isCurrent).finally(() => {
      if (isCurrent()) setRetrying(false);
    });
  };

  if (!activeGroup && !activeOwner) return <p>{t("dashboard.selectMember")}</p>;
  if (err) return <p style={{ color: "red" }}>{err}</p>;
  // A failed or empty history only replaces the charts below; the metrics
  // that did load must still render (#7629).
  if (!loaded) {
    return (
      <LoadingStatus label={t("app.loading")}>
        <PortfolioDashboardSkeleton />
      </LoadingStatus>
    );
  }

  // Whether the benchmark could not be fetched at all, as opposed to having
  // no overlapping prices; picks the fallback message (#7833).
  const benchmarkFailed = failedMetrics.includes("alpha");
  const perfUnavailable = failedMetrics.includes("performance");

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

  // Peak/trough are GBP portfolio values; shown in the reporting currency (#9805).
  const formatDrawdownNumber = (value: number | undefined | null) =>
    typeof value === "number" && Number.isFinite(value) ? reporting.format(value) : "—";

  // Fit the value axis to the series rather than 0 so movement is visible,
  // with currency ticks in the reporting currency (#7815).
  const valueDomain = paddedDomain(data.map((p) => p.value));
  const formatValueTick = (value: number) =>
    wholeMoney(reporting.convertGbp(value), reporting.currency, i18n.language);

  // The tile, this details text and the warnings below all derive from the
  // same classification, so an implausible drawdown is N/A everywhere and
  // gets the "unreliable" warning -- never a quoted percentage, and never
  // the ">90% drop" copy (which would be wrong for, say, +5%).
  const drawdownState = classifyDrawdown(maxDrawdown);
  const drawdownPercentText =
    drawdownState === "ok" || drawdownState === "severe"
      ? percent((maxDrawdown as number) * 100, 2, i18n.language)
      : null;
  const severeDrawdown = drawdownState === "severe";
  const unreliableDrawdown = drawdownState === "unreliable";

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

  const formatReturnTooltip = (v: unknown) =>
    percent(((v as number | undefined) ?? 0) * 100, 2, i18n.language);

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
        className={METRIC_LABEL_CLASS}
        style={{
          display: "flex",
          gap: "1rem",
          flexWrap: "wrap",
          fontSize: "0.9rem",
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
      {failedMetrics.length > 0 && (
        <p
          data-testid="performance-metrics-unavailable-warning"
          style={{
            fontSize: "0.85rem",
            color: "#facc15",
            marginBottom: "0.75rem",
          }}
        >
          {t("dashboard.performanceMetricsUnavailable", {
            metrics: failedMetrics.map((key) => t(METRIC_LABEL_KEYS[key])).join(", "),
          })}{" "}
          <button
            type="button"
            onClick={retryFailedMetrics}
            disabled={retrying}
            aria-busy={retrying}
            data-testid="performance-metrics-retry"
            style={{
              fontSize: "0.85rem",
              color: "#60a5fa",
              background: "transparent",
              border: "none",
              padding: 0,
              cursor: retrying ? "progress" : "pointer",
              textDecoration: "underline",
            }}
          >
            {t("common.retry")}
          </button>
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
          <div className={METRIC_LABEL_CLASS} style={{ fontSize: "0.9rem" }}>
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
            <FractionMetric value={alpha} range={RETURN_RANGE} testId="metric-alpha" />
          </div>
          <div className={METRIC_LABEL_CLASS} style={{ fontSize: "0.75rem" }}>
            {t("dashboard.vsBenchmark", "vs {{ticker}}", { ticker: BENCHMARK_TICKER })}
          </div>
          <ReturnBasisNote fields={returnBasis} className={METRIC_LABEL_CLASS} />
        </div>
        <div>
          <div className={METRIC_LABEL_CLASS} style={{ fontSize: "0.9rem" }}>
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
            <FractionMetric value={trackingError} range={TRACKING_ERROR_RANGE} testId="metric-tracking-error" />
          </div>
          <div className={METRIC_LABEL_CLASS} style={{ fontSize: "0.75rem" }}>
            {t("dashboard.vsBenchmark", "vs {{ticker}}", { ticker: BENCHMARK_TICKER })}
          </div>
        </div>
        <div>
          <div className={METRIC_LABEL_CLASS} style={{ fontSize: "0.9rem" }}>
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
              <FractionMetric value={maxDrawdown} range={DRAWDOWN_RANGE} testId="metric-max-drawdown" />
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
          <div className={METRIC_LABEL_CLASS} style={{ fontSize: "0.9rem" }}>
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
            <FractionMetric value={timeWeightedReturn} range={RETURN_RANGE} testId="metric-twr" />
          </div>
        </div>
        <div>
          <div className={METRIC_LABEL_CLASS} style={{ fontSize: "0.9rem" }}>
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
            <FractionMetric
              value={xirr}
              range={RETURN_RANGE}
              testId="metric-xirr"
              missingReason={t(
                "dashboard.xirrMissing",
                "XIRR can't be calculated for this period: it needs dated cash flows from your transaction history, and some patterns of flows have no solution.",
              )}
            />
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
            <p
              data-testid="drawdown-severe-warning"
              style={{ fontSize: "0.85rem", color: "#facc15", marginBottom: "0.75rem" }}
            >
              {t("dashboard.drawdownSuspicious")}
            </p>
          )}
          {unreliableDrawdown && (
            <p
              data-testid="drawdown-unreliable-warning"
              style={{ fontSize: "0.85rem", color: "#facc15", marginBottom: "0.75rem" }}
            >
              {t(
                "dashboard.drawdownUnreliable",
                "The max drawdown calculation returned an impossible value (a drawdown must lie between -100% and 0%), so it is not shown. This usually indicates missing or incorrect prices.",
              )}
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
              <Link to={diagnosticsHref} style={SECONDARY_LINK_STYLE}>
                {t("dashboard.openDiagnostics")}
              </Link>
            )}
            <Link to="/metrics-explained#max-drawdown" style={SECONDARY_LINK_STYLE}>
              {t("dashboard.viewMetricsExplanation")}
            </Link>
          </div>
        </div>
      )}
      {activeOwner && (
        <PortfolioFxAttribution
          owner={activeOwner}
          days={days === 0 ? 36500 : days}
          asOf={asOf}
        />
      )}
      <h2>{t("dashboard.portfolioValue")}</h2>
      {perfUnavailable ? (
        <p data-testid="performance-chart-unavailable">
          {t("dashboard.performanceUnavailable")}
        </p>
      ) : data.length === 0 ? (
        <p data-testid="performance-chart-empty">
          {t("dashboard.performanceEmpty")}
        </p>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={data}>
              <XAxis dataKey="date" />
              <YAxis
                domain={valueDomain ?? ["auto", "auto"]}
                tickFormatter={formatValueTick}
                width={80}
              />
              <Tooltip formatter={(v) => reporting.format(v as number | undefined)} />
              <Line type="monotone" dataKey="value" stroke="#8884d8" dot={false} />
            </LineChart>
          </ResponsiveContainer>

          <h2 style={{ marginTop: "2rem" }}>{t("dashboard.cumulativeReturn")}</h2>
          <p
            data-testid="twr-vs-cumulative"
            className={METRIC_LABEL_CLASS}
            style={{ fontSize: "0.8rem", marginTop: 0 }}
          >
            {t(
              "dashboard.twrVsCumulative",
              "Time-weighted return follows the holdings you actually held each day and strips out the timing of deposits and withdrawals, while this chart shows how your current holdings would have performed over the whole period, so the two can differ widely.",
            )}
          </p>
          {comparison.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={comparison}>
                  <XAxis dataKey="date" />
                  <YAxis tickFormatter={(v) => percent(v * 100, 2, i18n.language)} />
                  <Tooltip formatter={formatReturnTooltip} />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="portfolio"
                    name={t("dashboard.cumulativeReturnPortfolio")}
                    stroke={PORTFOLIO_LINE_COLOUR}
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="benchmark"
                    name={t("dashboard.cumulativeReturnBenchmark", { ticker: BENCHMARK_TICKER })}
                    stroke={BENCHMARK_LINE_COLOUR}
                    strokeDasharray="6 3"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
              <p
                data-testid="cumulative-return-basis"
                style={{ fontSize: "0.75rem", color: "#9ca3af", marginTop: "0.25rem" }}
              >
                {t("dashboard.cumulativeReturnBasis", {
                  ticker: BENCHMARK_TICKER,
                  from: comparison[0].date,
                  to: comparison[comparison.length - 1].date,
                })}
              </p>
            </>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={data}>
                  <XAxis dataKey="date" />
                  <YAxis tickFormatter={(v) => percent(v * 100, 2, i18n.language)} />
                  <Tooltip formatter={formatReturnTooltip} />
                  <Line
                    type="monotone"
                    dataKey="cumulative_return"
                    stroke={PORTFOLIO_LINE_COLOUR}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
              <p
                data-testid="benchmark-series-unavailable"
                style={{ fontSize: "0.8rem", color: "#facc15", marginTop: "0.25rem" }}
              >
                {benchmarkFailed
                  ? t("dashboard.benchmarkSeriesFailed", { ticker: BENCHMARK_TICKER })
                  : t("dashboard.benchmarkSeriesEmpty", { ticker: BENCHMARK_TICKER })}
              </p>
            </>
          )}
        </>
      )}
      {activeOwner && (
        <div style={{ marginTop: "1rem" }}>
          <Link to={diagnosticsHref} style={SECONDARY_LINK_STYLE}>
            {t("dashboard.openDiagnostics")}
          </Link>
        </div>
      )}
    </div>
  );
}

export default PerformanceDashboard;
