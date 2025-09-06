import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { percent, percentOrNa } from "../lib/money";
import metricStyles from "../styles/metrics.module.css";

type Props = {
  twr: number | null;
  irr: number | null;
  bestDay: number | null;
  worstDay: number | null;
  lastDay: number | null;
  alpha: number | null;
  trackingError: number | null;
  maxDrawdown: number | null;
  volatility: number | null;
  data: { date: string; value: number; cumulative_return: number }[];
};

function PortfolioDashboard({
  twr,
  irr,
  bestDay,
  worstDay,
  lastDay,
  alpha,
  trackingError,
  maxDrawdown,
  volatility,
  data,
}: Props) {
  return (
    <>
      <div className={metricStyles.metricContainer}>
        <div className={metricStyles.metricCard}>
          <div className={metricStyles.metricLabel}>TWR</div>
          <div className={metricStyles.metricValue}>
            {percent(twr != null ? twr * 100 : null)}
          </div>
        </div>
        <div className={metricStyles.metricCard}>
          <div className={metricStyles.metricLabel}>IRR</div>
          <div className={metricStyles.metricValue}>
            {percent(irr != null ? irr * 100 : null)}
          </div>
        </div>
        <div className={metricStyles.metricCard}>
          <div className={metricStyles.metricLabel}>Best Day</div>
          <div className={metricStyles.metricValue}>
            {percent(bestDay != null ? bestDay * 100 : null)}
          </div>
        </div>
        <div className={metricStyles.metricCard}>
          <div className={metricStyles.metricLabel}>Worst Day</div>
          <div className={metricStyles.metricValue}>
            {percent(worstDay != null ? worstDay * 100 : null)}
          </div>
        </div>
        <div className={metricStyles.metricCard}>
          <div className={metricStyles.metricLabel}>Last Day</div>
          <div className={metricStyles.metricValue}>
            {percent(lastDay != null ? lastDay * 100 : null)}
          </div>
        </div>
      </div>

      <div className={metricStyles.metricContainer}>
        <div className={metricStyles.metricCard}>
          <div className={metricStyles.metricLabel}>Alpha vs Benchmark</div>
          <div className={metricStyles.metricValue}>
            {percentOrNa(alpha != null ? alpha * 100 : null)}
          </div>
        </div>
        <div className={metricStyles.metricCard}>
          <div className={metricStyles.metricLabel}>Tracking Error</div>
          <div className={metricStyles.metricValue}>
            {percentOrNa(trackingError != null ? trackingError * 100 : null)}
          </div>
        </div>
        <div className={metricStyles.metricCard}>
          <div className={metricStyles.metricLabel}>Max Drawdown</div>
          <div className={metricStyles.metricValue}>
            {percentOrNa(maxDrawdown != null ? maxDrawdown * 100 : null)}
          </div>
        </div>
        <div className={metricStyles.metricCard}>
          <div className={metricStyles.metricLabel}>Volatility</div>
          <div className={metricStyles.metricValue}>
            {percentOrNa(volatility != null ? volatility * 100 : null)}
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

      <h2 className="mt-8">Cumulative Return</h2>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data}>
          <XAxis dataKey="date" />
          <YAxis tickFormatter={(v) => percent(v * 100)} />
          <Tooltip formatter={(v: number) => percent(v * 100)} />
          <Line
            type="monotone"
            dataKey="cumulative_return"
            stroke="#82ca9d"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </>
  );
}

export default PortfolioDashboard;

