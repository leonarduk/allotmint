import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import {
  LineChart,
  Line,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import { getPerformance, getPortfolioHoldings } from "../api";
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

const formatDays = (value: number | null | undefined) => {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  if (value === 0) return "same day";
  return `${value} ${value === 1 ? "day" : "days"}`;
};

export default function PerformanceDiagnostics() {
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

    history.forEach((point) => {
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
    });

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
            : "You appear to be offline.";
        setErr(message);
      });

    return () => {
      cancelled = true;
    };
  }, [owner]);

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
      <h1>Performance Diagnostics – {owner}</h1>
      {err ? (
        <div role="alert" aria-live="assertive" style={{ marginTop: "1rem" }}>
          <EmptyState message="We couldn't load performance diagnostics right now. Please try again later." />
          <p style={{ marginTop: "0.5rem", color: "#4b5563" }}>Error details: {err}</p>
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
                  <Tooltip formatter={(v: number) => percent(v * 100)} />
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
                  <h2 style={{ fontSize: "1rem", marginBottom: "0.5rem" }}>Current drawdown</h2>
                  <p style={{ fontSize: "1.5rem", fontWeight: 600 }}>{formatDrawdown(currentDrawdown)}</p>
                  {activeDrawdown ? (
                    <p style={{ color: "#9ca3af", marginTop: "0.5rem" }}>
                      Started {activeDrawdown.startDate} &ndash; trough {activeDrawdown.troughDate}
                    </p>
                  ) : (
                    <p style={{ color: "#9ca3af", marginTop: "0.5rem" }}>
                      Portfolio has fully recovered to a new high.
                    </p>
                  )}
                </div>
                <div style={{ border: "1px solid #374151", borderRadius: "0.5rem", padding: "1rem" }}>
                  <h2 style={{ fontSize: "1rem", marginBottom: "0.5rem" }}>Deepest drawdown</h2>
                  <p style={{ fontSize: "1.5rem", fontWeight: 600 }}>
                    {formatDrawdown(worstEvent?.maxDrawdown ?? null)}
                  </p>
                  {worstEvent ? (
                    <p style={{ color: "#9ca3af", marginTop: "0.5rem" }}>
                      {worstEvent.startDate} to {worstEvent.troughDate}
                    </p>
                  ) : (
                    <p style={{ color: "#9ca3af", marginTop: "0.5rem" }}>
                      No drawdowns met the {percent(THRESHOLD * 100)} threshold.
                    </p>
                  )}
                </div>
                <div style={{ border: "1px solid #374151", borderRadius: "0.5rem", padding: "1rem" }}>
                  <h2 style={{ fontSize: "1rem", marginBottom: "0.5rem" }}>Longest recovery</h2>
                  <p style={{ fontSize: "1.5rem", fontWeight: 600 }}>
                    {formatDays(longestRecovery?.recoveryDays ?? null)}
                  </p>
                  {longestRecovery ? (
                    <p style={{ color: "#9ca3af", marginTop: "0.5rem" }}>
                      {longestRecovery.troughDate} to {longestRecovery.recoveryDate}
                    </p>
                  ) : (
                    <p style={{ color: "#9ca3af", marginTop: "0.5rem" }}>
                      No completed recoveries in this period.
                    </p>
                  )}
                </div>
                <div style={{ border: "1px solid #374151", borderRadius: "0.5rem", padding: "1rem" }}>
                  <h2 style={{ fontSize: "1rem", marginBottom: "0.5rem" }}>Average recovery</h2>
                  <p style={{ fontSize: "1.5rem", fontWeight: 600 }}>
                    {formatDays(averageRecoveryDays)}
                  </p>
                  <p style={{ color: "#9ca3af", marginTop: "0.5rem" }}>
                    Across {eventsForSummary.filter((event) => event.recoveryDays !== null).length} historical recoveries
                  </p>
                </div>
              </div>
              <div style={{ marginTop: "1.5rem" }}>
                <h2>Drawdown events</h2>
                {drawdownEvents.length === 0 ? (
                  <p style={{ color: "#9ca3af", marginTop: "0.5rem" }}>
                    We didn't find any periods where the portfolio fell below its previous peak.
                  </p>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "0.75rem" }}>
                      <thead>
                        <tr>
                          <th style={{ textAlign: "left", padding: "0.5rem", borderBottom: "1px solid #374151" }}>
                            Start
                          </th>
                          <th style={{ textAlign: "left", padding: "0.5rem", borderBottom: "1px solid #374151" }}>
                            Trough
                          </th>
                          <th style={{ textAlign: "right", padding: "0.5rem", borderBottom: "1px solid #374151" }}>
                            Depth
                          </th>
                          <th style={{ textAlign: "right", padding: "0.5rem", borderBottom: "1px solid #374151" }}>
                            Days to trough
                          </th>
                          <th style={{ textAlign: "left", padding: "0.5rem", borderBottom: "1px solid #374151" }}>
                            Recovery
                          </th>
                          <th style={{ textAlign: "right", padding: "0.5rem", borderBottom: "1px solid #374151" }}>
                            Recovery length
                          </th>
                          <th style={{ padding: "0.5rem", borderBottom: "1px solid #374151" }}>Action</th>
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
                              {formatDays(event.daysToTrough)}
                            </td>
                            <td style={{ padding: "0.5rem", borderBottom: "1px solid #1f2937" }}>
                              {event.recoveryDate ?? "Still recovering"}
                            </td>
                            <td
                              style={{
                                padding: "0.5rem",
                                borderBottom: "1px solid #1f2937",
                                textAlign: "right",
                              }}
                            >
                              {formatDays(event.recoveryDays)}
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
                                Inspect holdings
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
              <EmptyState message="We don't have performance history for this owner yet." />
            </div>
          )}
          {issues.length > 0 && (
            <div style={{ marginTop: "1rem" }}>
              <h2>Data quality report</h2>
              <p style={{ color: "#4b5563" }}>
                We ignored {issues.length === 1 ? "one date" : `${issues.length} dates`} where
                the reconstructed portfolio value temporarily collapsed to nearly zero. Please
                review pricing for:
              </p>
              <ul>
                {issues.map((issue) => (
                  <li key={issue.date}>
                    <strong>{issue.date}</strong>: value {issue.value.toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                    {" "}(prev {issue.previousValue.toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}, next {issue.nextValue.toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })})
                  </li>
                ))}
              </ul>
            </div>
          )}
          {selected && (
            <div style={{ marginTop: "1rem" }}>
              <h2>Holdings on {selected}</h2>
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
                  No holdings were reported for this date. Try another point in the timeline.
                </p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
