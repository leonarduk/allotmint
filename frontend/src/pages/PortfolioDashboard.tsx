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
import { Link } from "react-router-dom";

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
  owner?: string;
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
  owner,
}: Props) {
  void owner;
  return (
    <>
      <div className="grid grid-cols-2 gap-4 p-4 mb-4 bg-gray-900 border border-gray-700 rounded sm:grid-cols-3 md:grid-cols-5">
        <div className="flex flex-col">
          <div className="text-sm text-gray-400">TWR</div>
          <div className="text-lg font-bold">
            {percent(twr != null ? twr * 100 : null)}
          </div>
        </div>
        <div className="flex flex-col">
          <div className="text-sm text-gray-400">IRR</div>
          <div className="text-lg font-bold">
            {percent(irr != null ? irr * 100 : null)}
          </div>
        </div>
        <div className="flex flex-col">
          <div className="text-sm text-gray-400">Best Day</div>
          <div className="text-lg font-bold">
            {percent(bestDay != null ? bestDay * 100 : null)}
          </div>
        </div>
        <div className="flex flex-col">
          <div className="text-sm text-gray-400">Worst Day</div>
          <div className="text-lg font-bold">
            {percent(worstDay != null ? worstDay * 100 : null)}
          </div>
        </div>
        <div className="flex flex-col">
          <div className="text-sm text-gray-400">Last Day</div>
          <div className="text-lg font-bold">
            {percent(lastDay != null ? lastDay * 100 : null)}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 p-4 mb-4 bg-gray-900 border border-gray-700 rounded sm:grid-cols-4">
        <div className="flex flex-col">
          <div className="text-sm text-gray-400">Alpha vs Benchmark</div>
          <div className="text-lg font-bold">
            {percentOrNa(alpha)}
          </div>
        </div>
        <div className="flex flex-col">
          <div className="text-sm text-gray-400">Tracking Error</div>
          <div className="text-lg font-bold">
            {percentOrNa(trackingError)}
          </div>
        </div>
        <div className="flex flex-col">
          <div className="text-sm text-gray-400">Max Drawdown</div>
          <div className="text-lg font-bold">
            {percentOrNa(maxDrawdown)}
          </div>
        </div>
        <div className="flex flex-col">
          <div className="text-sm text-gray-400">Volatility</div>
          <div className="text-lg font-bold">
            {percentOrNa(volatility)}
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
      <p className="mt-8">
        <Link to="/goals">View Goals</Link> |{" "}
        <Link to="/pension/forecast">Pension Forecast</Link>
      </p>
    </>
  );
}

export default PortfolioDashboard;

