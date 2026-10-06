import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import {
  LineChart,
  Line,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import { getPerformance, getPortfolioHoldings } from "../api";
import Menu from "../components/Menu";
import type {
  PerformancePoint,
  HoldingValue,
  DataQualityIssue,
} from "../types";
import { percent } from "../lib/money";
import EmptyState from "../components/EmptyState";

const THRESHOLD = 0.1; // highlight drops worse than -10%

interface DrawdownEvent {
  startDate: string;
  troughDate: string;
  recoveryDate: string | null;
  maxDrawdown: number;
  daysToTrough: number;
  recoveryDays: number | null;
  durationDays: number;
}

const money2 = (v: number) =>
  v.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

const toDate = (value: string) => new Date(`${value}T00:00:00Z`);

const differenceInDays = (start: string, end: string) => {
  const startDate = toDate(start);
  const endDate = toDate(end);
  const diff = Math.round((endDate.getTime() - startDate.getTime()) / 86_400_000);
  return Number.isFinite(diff) ? Math.max(diff, 0) : 0;
};

const formatDrawdown = (value: number | null | undefined) => {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return percent(Math.abs(value) * 100);
};

const formatDays = (t: TFunction, value: number | null | undefined) => {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  if (value === 0) return t("performanceDiagnostics.sameDay");
  return t("performanceDiagnostics.days", { count: value });
};

export default function PerformanceDiagnostics() {
  const { t } = useTranslation();
  const { owner = "" } = useParams<{ owner: string }>();
  const [history, setHistory] = useState<PerformancePoint[]>([]);
  const [holdings, setHoldings] = useState<HoldingValue[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [issues, setIssues] = useState<DataQualityIssue[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const drawdownEvents = useMemo(() => {
    if (!history.length) return [];

    const events: DrawdownEvent[] = [];
    type ActiveEvent = {
      startDate: string;
      troughDate: string;
      lastDate: string;
      maxDrawdown: number;
    } | null;

    let current: ActiveEvent = null;

    for (const point of history) {
      const drawdownValue =
        typeof point.drawdown === "number" && Number.isFinite(point.drawdown)
          ? point.drawdown
          : 0;
      const date = point.date;

      if (drawdownValue < 0) {
        if (!current) {
          current = {
            startDate: date,
            troughDate: date,
            lastDate: date,
            maxDrawdown: drawdownValue,
          };
        } else {
          if (drawdownValue < current.maxDrawdown) {
            current.maxDrawdown = drawdownValue;
            current.troughDate = date;
          }
          current.lastDate = date;
        }
      } else if (current) {
        const startDate = current.startDate;
        const troughDate = current.troughDate;
        const recoveryDate = date;
        events.push({
          startDate,
          troughDate,
          recoveryDate,
          maxDrawdown: current.maxDrawdown,
          daysToTrough: differenceInDays(startDate, troughDate),
          recoveryDays: differenceInDays(troughDate, recoveryDate),
          durationDays: differenceInDays(startDate, recoveryDate),
        });
        current = null;
      }
    }

    if (current) {
      const lastDate = current.lastDate || history[history.length - 1].date;
      events.push({
        startDate: current.startDate,
        troughDate: current.troughDate,
        recoveryDate: null,
        maxDrawdown: current.maxDrawdown,
        daysToTrough: differenceInDays(current.startDate, current.troughDate),
        recoveryDays: null,
        durationDays: differenceInDays(current.startDate, lastDate),
      });
    }

    return events;
  }, [history]);

  const significantEvents = useMemo(
    () => drawdownEvents.filter((event) => event.maxDrawdown <= -THRESHOLD),
    [drawdownEvents],
  );

  const eventsForSummary = significantEvents.length > 0 ? significantEvents : drawdownEvents;

  const worstEvent = useMemo(() => {
    if (!eventsForSummary.length) return null;
    return eventsForSummary.reduce((worst, event) =>
      event.maxDrawdown < worst.maxDrawdown ? event : worst,
    );
  }, [eventsForSummary]);

  const longestRecovery = useMemo(() => {
    const completed = eventsForSummary.filter((event) => event.recoveryDays !== null);
    if (!completed.length) return null;
    return completed.reduce((longest, event) =>
      (event.recoveryDays ?? 0) > (longest.recoveryDays ?? 0) ? event : longest,
    );
  }, [eventsForSummary]);

  const averageRecoveryDays = useMemo(() => {
    const completed = eventsForSummary.filter((event) => event.recoveryDays !== null);
    if (!completed.length) return null;
    const total = completed.reduce((sum, event) => sum + (event.recoveryDays ?? 0), 0);
    return Math.round(total / completed.length);
  }, [eventsForSummary]);

  const currentDrawdown = useMemo(() => {
    const latest = history.at(-1);
    return typeof latest?.drawdown === "number" ? latest.drawdown : null;
  }, [history]);

  const activeDrawdown = useMemo(
    () => drawdownEvents.find((event) => event.recoveryDate === null) ?? null,
    [drawdownEvents],
  );

  const renderDrawdownTooltip = ({
    active,
    payload,
    label,
  }: {
    active?: boolean;
    payload?: ReadonlyArray<{ payload?: PerformancePoint }>;
    label?: string | number;
  }) => {
    if (!active || !payload?.length) return null;
    const point = payload[0]?.payload;
    const dateLabel = typeof label === "string" && label.length > 0 ? label : point?.date ?? "—";
    const drawdownValue =
      typeof point?.drawdown === "number" && Number.isFinite(point.drawdown)
        ? point.drawdown
        : null;
    return (
      <div
        style={{
          backgroundColor: "#ffffff",
          border: "1px solid #d1d5db",
          borderRadius: "0.5rem",
          color: "#1f2937",
          padding: "0.5rem 0.75rem",
        }}
      >
        <p style={{ margin: 0, fontSize: "0.85rem", fontWeight: 600 }}>{t('performanceDiagnostics.tooltipDate', { date: dateLabel })}</p>
        <p style={{ margin: "0.25rem 0 0", fontSize: "0.85rem" }}>
          {t('performanceDiagnostics.tooltipDrawdown', {
            value: percent((drawdownValue ?? 0) * 100),
          })}
        </p>
      </div>
    );
  };

  useEffect(() => {
    if (!owner) {
      setHistory([]);
      setHoldings([]);
      setSelected(null);
      setIssues([]);
      setErr(null);
      return;
    }

    let cancelled = false;
    setErr(null);
    setHistory([]);
    setHoldings([]);
    setSelected(null);
    setIssues([]);

    getPerformance(owner)
      .then((res) => {
        if (cancelled) return;
        setHistory(res.history);
        setIssues(res.dataQualityIssues ?? []);
      })
      .catch((e) => {
        if (cancelled) return;
        setHistory([]);
        setHoldings([]);
        setSelected(null);
        setIssues([]);
        const message =
          navigator.onLine
            ? e instanceof Error
              ? e.message
              : String(e)
            : t("performanceDiagnostics.offline");
        setErr(message);
      });

    return () => {
      cancelled = true;
    };
  }, [owner, t]);

  const handleClick = async (date: string) => {
    try {
      const res = await getPortfolioHoldings(owner, date);
      setHoldings(res.holdings);
      setSelected(date);
      setErr(null);
    } catch (e) {
      setHoldings([]);
      setSelected(null);
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div style={{ padding: "1rem" }}>
      <div style={{ marginBottom: "1rem" }}>
        <Menu selectedOwner={owner} />
      </div>
      <h1>{t('performanceDiagnostics.title', { owner })}</h1>
      {err ? (
        <div role="alert" aria-live="assertive" style={{ marginTop: "1rem" }}>
          <EmptyState message={t('performanceDiagnostics.loadError')} />
          <p style={{ marginTop: "0.5rem", color: "#4b5563" }}>{t('performanceDiagnostics.errorDetails', { error: err })}</p>
        </div>
      ) : (
        <>
          {history.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={240}>
                <LineChart
                  data={history}
                  onClick={(e) => {
                    if (e && (e as any).activeLabel) handleClick((e as any).activeLabel);
                  }}
                >
                  <XAxis dataKey="date" />
                  <YAxis tickFormatter={(v) => percent(v * 100)} />
                  <Tooltip content={renderDrawdownTooltip} />
                  <Line
                    type="monotone"
                    dataKey="drawdown"
                    stroke="#8884d8"
                    dot={({ cx, cy, payload }) => (
                      <circle
                        cx={cx}
                        cy={cy}
                        r={payload.drawdown < -THRESHOLD ? 4 : 2}
                        fill={payload.drawdown < -THRESHOLD ? "red" : "#8884d8"}
                      />
                    )}
                  />
                </LineChart>
              </ResponsiveContainer>
              <div
                style={{
                  display: "grid",
                  gap: "1rem",
                  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                  marginTop: "1.5rem",
                }}
              >
                <div style={{ border: "1px solid #374151", borderRadius: "0.5rem", padding: "1rem" }}>
                  <h2 style={{ fontSize: "1rem", marginBottom: "0.5rem" }}>{t('performanceDiagnostics.currentDrawdown')}</h2>
                  <p style={{ fontSize: "1.5rem", fontWeight: 600 }}>{formatDrawdown(currentDrawdown)}</p>
                  {activeDrawdown ? (
                    <p style={{ color: "#9ca3af", marginTop: "0.5rem" }}>
                      {t('performanceDiagnostics.startedTrough', {
                        start: activeDrawdown.startDate,
                        trough: activeDrawdown.troughDate,
                      })}
                    </p>
                  ) : (
                    <p style={{ color: "#9ca3af", marginTop: "0.5rem" }}>
                      {t('performanceDiagnostics.fullyRecovered')}
                    </p>
                  )}
                </div>
                <div style={{ border: "1px solid #374151", borderRadius: "0.5rem", padding: "1rem" }}>
                  <h2 style={{ fontSize: "1rem", marginBottom: "0.5rem" }}>{t('performanceDiagnostics.deepestDrawdown')}</h2>
                  <p style={{ fontSize: "1.5rem", fontWeight: 600 }}>
                    {formatDrawdown(worstEvent?.maxDrawdown ?? null)}
                  </p>
                  {worstEvent ? (
                    <p style={{ color: "#9ca3af", marginTop: "0.5rem" }}>
                      {t('performanceDiagnostics.dateRange', {
                        from: worstEvent.startDate,
                        to: worstEvent.troughDate,
                      })}
                    </p>
                  ) : (
                    <p style={{ color: "#9ca3af", marginTop: "0.5rem" }}>
                      {t('performanceDiagnostics.noDrawdowns', {
                        threshold: percent(THRESHOLD * 100),
                      })}
                    </p>
                  )}
                </div>
                <div style={{ border: "1px solid #374151", borderRadius: "0.5rem", padding: "1rem" }}>
                  <h2 style={{ fontSize: "1rem", marginBottom: "0.5rem" }}>{t('performanceDiagnostics.longestRecovery')}</h2>
                  <p style={{ fontSize: "1.5rem", fontWeight: 600 }}>
                    {formatDays(t, longestRecovery?.recoveryDays ?? null)}
                  </p>
                  {longestRecovery ? (
                    <p style={{ color: "#9ca3af", marginTop: "0.5rem" }}>
                      {t('performanceDiagnostics.dateRange', {
                        from: longestRecovery.troughDate,
                        to: longestRecovery.recoveryDate,
                      })}
                    </p>
                  ) : (
                    <p style={{ color: "#9ca3af", marginTop: "0.5rem" }}>
                      {t('performanceDiagnostics.noRecoveries')}
                    </p>
                  )}
                </div>
                <div style={{ border: "1px solid #374151", borderRadius: "0.5rem", padding: "1rem" }}>
                  <h2 style={{ fontSize: "1rem", marginBottom: "0.5rem" }}>{t('performanceDiagnostics.averageRecovery')}</h2>
                  <p style={{ fontSize: "1.5rem", fontWeight: 600 }}>
                    {formatDays(t, averageRecoveryDays)}
                  </p>
                  <p style={{ color: "#9ca3af", marginTop: "0.5rem" }}>
                    {t('performanceDiagnostics.acrossRecoveries', {
                      count: eventsForSummary.filter(
                        (event) => event.recoveryDays !== null,
                      ).length,
                    })}
                  </p>
                </div>
              </div>
              <div style={{ marginTop: "1.5rem" }}>
                <h2>{t('performanceDiagnostics.drawdownEvents')}</h2>
                {drawdownEvents.length === 0 ? (
                  <p style={{ color: "#9ca3af", marginTop: "0.5rem" }}>
                    {t('performanceDiagnostics.noEvents')}
                  </p>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "0.75rem" }}>
                      <thead>
                        <tr>
                          <th style={{ textAlign: "left", padding: "0.5rem", borderBottom: "1px solid #374151" }}>
                            {t('performanceDiagnostics.colStart')}
                          </th>
                          <th style={{ textAlign: "left", padding: "0.5rem", borderBottom: "1px solid #374151" }}>
                            {t('performanceDiagnostics.colTrough')}
                          </th>
                          <th style={{ textAlign: "right", padding: "0.5rem", borderBottom: "1px solid #374151" }}>
                            {t('performanceDiagnostics.colDepth')}
                          </th>
                          <th style={{ textAlign: "right", padding: "0.5rem", borderBottom: "1px solid #374151" }}>
                            {t('performanceDiagnostics.colDaysToTrough')}
                          </th>
                          <th style={{ textAlign: "left", padding: "0.5rem", borderBottom: "1px solid #374151" }}>
                            {t('performanceDiagnostics.colRecovery')}
                          </th>
                          <th style={{ textAlign: "right", padding: "0.5rem", borderBottom: "1px solid #374151" }}>
                            {t('performanceDiagnostics.colRecoveryLength')}
                          </th>
                          <th style={{ padding: "0.5rem", borderBottom: "1px solid #374151" }}>
                            {t('performanceDiagnostics.colAction')}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {drawdownEvents.map((event) => (
                          <tr key={`${event.startDate}-${event.troughDate}`}>
                            <td style={{ padding: "0.5rem", borderBottom: "1px solid #1f2937" }}>{
                              event.startDate
                            }</td>
                            <td style={{ padding: "0.5rem", borderBottom: "1px solid #1f2937" }}>{
                              event.troughDate
                            }</td>
                            <td
                              style={{
                                padding: "0.5rem",
                                borderBottom: "1px solid #1f2937",
                                textAlign: "right",
                              }}
                            >
                              {formatDrawdown(event.maxDrawdown)}
                            </td>
                            <td
                              style={{
                                padding: "0.5rem",
                                borderBottom: "1px solid #1f2937",
                                textAlign: "right",
                              }}
                            >
                              {formatDays(t, event.daysToTrough)}
                            </td>
                            <td style={{ padding: "0.5rem", borderBottom: "1px solid #1f2937" }}>
                              {event.recoveryDate ?? t("performanceDiagnostics.stillRecovering")}
                            </td>
                            <td
                              style={{
                                padding: "0.5rem",
                                borderBottom: "1px solid #1f2937",
                                textAlign: "right",
                              }}
                            >
                              {formatDays(t, event.recoveryDays)}
                            </td>
                            <td style={{ padding: "0.5rem", borderBottom: "1px solid #1f2937" }}>
                              <button
                                type="button"
                                onClick={() => handleClick(event.troughDate)}
                                style={{
                                  background: "#1f2937",
                                  color: "#f9fafb",
                                  border: "1px solid #4b5563",
                                  borderRadius: "0.375rem",
                                  padding: "0.35rem 0.75rem",
                                  cursor: "pointer",
                                }}
                              >
                                {t('performanceDiagnostics.inspectHoldings')}
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div style={{ marginTop: "1rem" }}>
              <EmptyState message={t('performanceDiagnostics.noHistory')} />
            </div>
          )}
          {issues.length > 0 && (
            <div style={{ marginTop: "1rem" }}>
              <h2>{t('performanceDiagnostics.dataQualityReport')}</h2>
              <p style={{ color: "#4b5563" }}>
                {t('performanceDiagnostics.ignoredDates', {
                  count: issues.length,
                })}
              </p>
              <ul>
                {issues.map((issue) => (
                  <li key={issue.date}>
                    <strong>{issue.date}</strong>
                    {t('performanceDiagnostics.issueLine', {
                      value: money2(issue.value),
                      prev: money2(issue.previousValue),
                      next: money2(issue.nextValue),
                    })}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {selected && (
            <div style={{ marginTop: "1rem" }}>
              <h2>{t('performanceDiagnostics.holdingsOn', { date: selected })}</h2>
              {holdings.length > 0 ? (
                <ul>
                  {holdings.map((h, index) => (
                    <li key={`${h.ticker}.${h.exchange}.${index}`}>
                      <a
                        href={`/timeseries?ticker=${encodeURIComponent(
                          h.ticker,
                        )}&exchange=${encodeURIComponent(h.exchange)}`}
                      >
                        {h.ticker}.{h.exchange}
                      </a>
                      : {h.units} @ {h.price ?? "n/a"} = {h.value ?? "n/a"}
                    </li>
                  ))}
                </ul>
              ) : (
                <p style={{ color: "#9ca3af" }}>
                  {t('performanceDiagnostics.noHoldings')}
                </p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
