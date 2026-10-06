import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { percent } from "../lib/money";
import FractionMetric from "../components/FractionMetric";
import {
  DRAWDOWN_RANGE,
  RETURN_RANGE,
  TRACKING_ERROR_RANGE,
  VOLATILITY_RANGE,
} from "../lib/metricPlausibility";
// import metricStyles from "../styles/metrics.module.css";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

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
  const { t } = useTranslation();
  return (
    <>
      <div className="grid grid-cols-2 gap-4 p-4 mb-4 bg-gray-900 border border-gray-700 rounded sm:grid-cols-3 md:grid-cols-5">
        <div className="flex flex-col">
          <div className="text-sm text-gray-400">{t('portfolioDashboard.twr')}</div>
          <div className="text-lg font-bold">
            {percent(twr != null ? twr * 100 : null)}
          </div>
        </div>
        <div className="flex flex-col">
          <div className="text-sm text-gray-400">{t('portfolioDashboard.irr')}</div>
          <div className="text-lg font-bold">
            {percent(irr != null ? irr * 100 : null)}
          </div>
        </div>
        <div className="flex flex-col">
          <div className="text-sm text-gray-400">{t('portfolioDashboard.bestDay')}</div>
          <div className="text-lg font-bold">
            {percent(bestDay != null ? bestDay * 100 : null)}
          </div>
        </div>
        <div className="flex flex-col">
          <div className="text-sm text-gray-400">{t('portfolioDashboard.worstDay')}</div>
          <div className="text-lg font-bold">
            {percent(worstDay != null ? worstDay * 100 : null)}
          </div>
        </div>
        <div className="flex flex-col">
          <div className="text-sm text-gray-400">{t('portfolioDashboard.lastDay')}</div>
          <div className="text-lg font-bold">
            {percent(lastDay != null ? lastDay * 100 : null)}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 p-4 mb-4 bg-gray-900 border border-gray-700 rounded sm:grid-cols-4">
        <div className="flex flex-col">
          <div className="text-sm text-gray-400">{t('portfolioDashboard.alpha')}</div>
          <div className="text-lg font-bold">
            <FractionMetric value={alpha} range={RETURN_RANGE} testId="metric-alpha" />
          </div>
        </div>
        <div className="flex flex-col">
          <div className="text-sm text-gray-400">{t('portfolioDashboard.trackingError')}</div>
          <div className="text-lg font-bold">
            <FractionMetric value={trackingError} range={TRACKING_ERROR_RANGE} testId="metric-tracking-error" />
          </div>
        </div>
        <div className="flex flex-col">
          <div className="text-sm text-gray-400">{t('portfolioDashboard.maxDrawdown')}</div>
          <div className="text-lg font-bold">
            <FractionMetric value={maxDrawdown} range={DRAWDOWN_RANGE} testId="metric-max-drawdown" />
          </div>
        </div>
        <div className="flex flex-col">
          <div className="text-sm text-gray-400">{t('portfolioDashboard.volatility')}</div>
          <div className="text-lg font-bold">
            <FractionMetric value={volatility} range={VOLATILITY_RANGE} testId="metric-volatility" />
          </div>
        </div>
      </div>

      <h2>{t('portfolioDashboard.portfolioValue')}</h2>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data}>
          <XAxis dataKey="date" />
          <YAxis />
          <Tooltip />
          <Line type="monotone" dataKey="value" stroke="#8884d8" dot={false} />
        </LineChart>
      </ResponsiveContainer>

      <h2 className="mt-8">{t('portfolioDashboard.cumulativeReturn')}</h2>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data}>
          <XAxis dataKey="date" />
          <YAxis tickFormatter={(v) => percent(v * 100)} />
          <Tooltip formatter={(v) => percent(((v as number | undefined) ?? 0) * 100)} />
          <Line
            type="monotone"
            dataKey="cumulative_return"
            stroke="#82ca9d"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
      <p className="mt-8">
        <Link
          to={
            owner
              ? `/returns/compare?owner=${encodeURIComponent(owner)}`
              : "/returns/compare"
          }
        >
          {t('portfolioDashboard.returnComparison')}
        </Link>{" "}
        | <Link to="/goals">{t('portfolioDashboard.viewGoals')}</Link> |{" "}
        <Link to="/pension/forecast">{t('portfolioDashboard.pensionForecast')}</Link>
      </p>
    </>
  );
}

export default PortfolioDashboard;

