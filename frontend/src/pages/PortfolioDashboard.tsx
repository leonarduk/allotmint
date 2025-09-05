import { useEffect, useState } from 'react';
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  getPerformance,
  getAlphaVsBenchmark,
  getTrackingError,
  getMaxDrawdown,
} from '../api';
import type { PerformancePoint } from '../types';
import { percent } from '../lib/money';
import i18n from '../i18n';

interface Props {
  owner: string | null;
}

export function PortfolioDashboard({ owner }: Props) {
  const [data, setData] = useState<PerformancePoint[]>([]);
  const [alpha, setAlpha] = useState<number | null>(null);
  const [trackingError, setTrackingError] = useState<number | null>(null);
  const [maxDrawdown, setMaxDrawdown] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [days, setDays] = useState<number>(365);
  const [excludeCash, setExcludeCash] = useState<boolean>(false);

  useEffect(() => {
    if (!owner) return;
    setErr(null);
    setData([]);
    const reqDays = days === 0 ? 36500 : days;
    Promise.all([
      getPerformance(owner, reqDays, excludeCash),
      getAlphaVsBenchmark(owner, 'VWRL.L', reqDays),
      getTrackingError(owner, 'VWRL.L', reqDays),
      getMaxDrawdown(owner, reqDays),
    ])
      .then(([perf, alphaRes, teRes, mdRes]) => {
        setData(perf);
        setAlpha(alphaRes.alpha_vs_benchmark);
        setTrackingError(teRes.tracking_error);
        setMaxDrawdown(mdRes.max_drawdown);
      })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [owner, days, excludeCash]);

  if (!owner) return <p>Select a member.</p>;
  if (err) return <p style={{ color: 'red' }}>{err}</p>;
  if (!data.length) return <p>Loading…</p>;

  const last = data[data.length - 1];
  const twr = last.cumulative_return ?? null;
  const n = data.length;
  const irr = twr != null && n > 1 ? Math.pow(1 + twr, 365 / n) - 1 : null;

  const dailyReturns = data
    .map((p) => p.daily_return)
    .filter((v): v is number => v != null);
  const lastDay = dailyReturns.length
    ? dailyReturns[dailyReturns.length - 1]
    : null;
  const bestDay = dailyReturns.length ? Math.max(...dailyReturns) : null;
  const worstDay = dailyReturns.length ? Math.min(...dailyReturns) : null;
  let volatility: number | null = null;
  if (dailyReturns.length > 1) {
    const mean =
      dailyReturns.reduce((sum, v) => sum + v, 0) / dailyReturns.length;
    const variance =
      dailyReturns.reduce((sum, v) => sum + (v - mean) ** 2, 0) /
      (dailyReturns.length - 1);
    volatility = Math.sqrt(variance);
  }
  // eslint-disable-next-line prefer-const
  return (
    <div style={{ marginTop: '1rem' }}>
      <div style={{ marginBottom: '0.5rem' }}>
        <label style={{ fontSize: '0.85rem' }}>
          Range:
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            style={{ marginLeft: '0.25rem' }}
          >
            <option value={7}>1W</option>
            <option value={30}>1M</option>
            <option value={365}>1Y</option>
            <option value={3650}>10Y</option>
            <option value={0}>MAX</option>
          </select>
        </label>
        <label style={{ fontSize: '0.85rem', marginLeft: '1rem' }}>
          Exclude cash
          <input
            type="checkbox"
            checked={excludeCash}
            onChange={(e) => setExcludeCash(e.target.checked)}
            style={{ marginLeft: '0.25rem' }}
          />
        </label>
      </div>

      <div
        style={{
          display: 'flex',
          gap: '2rem',
          marginBottom: '1rem',
          padding: '0.75rem 1rem',
          backgroundColor: '#222',
          border: '1px solid #444',
          borderRadius: '6px',
        }}
      >
        <div>
          <div style={{ fontSize: '0.9rem', color: '#aaa' }}>TWR</div>
          <div style={{ fontSize: '1.2rem', fontWeight: 'bold' }}>
            {percent(twr != null ? twr * 100 : null)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '0.9rem', color: '#aaa' }}>IRR</div>
          <div style={{ fontSize: '1.2rem', fontWeight: 'bold' }}>
            {percent(irr != null ? irr * 100 : null)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '0.9rem', color: '#aaa' }}>Best Day</div>
          <div style={{ fontSize: '1.2rem', fontWeight: 'bold' }}>
            {percent(bestDay != null ? bestDay * 100 : null)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '0.9rem', color: '#aaa' }}>Worst Day</div>
          <div style={{ fontSize: '1.2rem', fontWeight: 'bold' }}>
            {percent(worstDay != null ? worstDay * 100 : null)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '0.9rem', color: '#aaa' }}>Last Day</div>
          <div style={{ fontSize: '1.2rem', fontWeight: 'bold' }}>
            {percent(lastDay != null ? lastDay * 100 : null)}
          </div>
        </div>
      </div>

      <div
        style={{
          display: 'flex',
          gap: '2rem',
          marginBottom: '1rem',
          padding: '0.75rem 1rem',
          backgroundColor: '#222',
          border: '1px solid #444',
          borderRadius: '6px',
        }}
      >
        <div>
          <div style={{ fontSize: '0.9rem', color: '#aaa' }}>
            Alpha vs Benchmark
          </div>
          <div style={{ fontSize: '1.2rem', fontWeight: 'bold' }}>
            {percent(alpha != null ? alpha * 100 : null)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '0.9rem', color: '#aaa' }}>
            Tracking Error
          </div>
          <div style={{ fontSize: '1.2rem', fontWeight: 'bold' }}>
            {percent(trackingError != null ? trackingError * 100 : null)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '0.9rem', color: '#aaa' }}>Max Drawdown</div>
          <div style={{ fontSize: '1.2rem', fontWeight: 'bold' }}>
            {percent(maxDrawdown != null ? maxDrawdown * 100 : null)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '0.9rem', color: '#aaa' }}>Volatility</div>
          <div style={{ fontSize: '1.2rem', fontWeight: 'bold' }}>
            {percent(volatility != null ? volatility * 100 : null)}
          </div>
        </div>
      </div>

      <h2>Portfolio Value</h2>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data}>
          <XAxis dataKey="date" />
          <YAxis />
          <Tooltip />
          <Line type="monotone" dataKey="value" stroke="#8884d8" dot={false} />
        </LineChart>
      </ResponsiveContainer>

      <h2 style={{ marginTop: '2rem' }}>Cumulative Return</h2>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data}>
          <XAxis dataKey="date" />
          <YAxis tickFormatter={(v) => percent(v * 100, 2, i18n.language)} />
          <Tooltip
            formatter={(v: number) => percent(v * 100, 2, i18n.language)}
          />
          <Line
            type="monotone"
            dataKey="cumulative_return"
            stroke="#82ca9d"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default PortfolioDashboard;
