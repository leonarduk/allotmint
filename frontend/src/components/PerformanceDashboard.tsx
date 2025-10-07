import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  getPerformance,
  getAlphaVsBenchmark,
  getTrackingError,
  getMaxDrawdown,
} from "../api";
import type { PerformancePoint } from "../types";
import { percent, percentOrNa } from "../lib/money";
import { formatDateISO } from "../lib/date";

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
  const [timeWeightedReturn, setTimeWeightedReturn] = useState<number | null>(
    null,
  );
  const [xirr, setXirr] = useState<number | null>(null);
  const [excludeCash, setExcludeCash] = useState<boolean>(false);
  const [reportingDate, setReportingDate] = useState<string | null>(null);
  const [previousDate, setPreviousDate] = useState<string | null>(null);
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();

  useEffect(() => {
    if (!owner) return;
    setErr(null);
    setData([]);
    setReportingDate(null);
    setPreviousDate(null);
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
        setTimeWeightedReturn(perf.time_weighted_return ?? null);
        setXirr(perf.xirr ?? null);
        setReportingDate(perf.reportingDate ?? null);
        setPreviousDate(perf.previousDate ?? null);
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
          <div style={{ fontSize: "1.1rem", fontWeight: "bold" }}>
            {percentOrNa(safeMaxDrawdown)}
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
      <div style={{ marginTop: "1rem" }}>
        <button
          disabled={!owner}
          onClick={() => owner && navigate(`/performance/${owner}/diagnostics`)}
        >
          Drill down
        </button>
      </div>
    </div>
  );
}

export default PerformanceDashboard;
