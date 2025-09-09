import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getMarketOverview } from '../api';
import type { MarketOverview as MarketOverviewData } from '../types';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
} from 'recharts';

export default function MarketOverview() {
  const { t } = useTranslation();
  const [data, setData] = useState<MarketOverviewData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getMarketOverview()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p>{t('common.loading')}</p>;
  if (error) return <p className="text-red-500">{error}</p>;
  if (!data) return null;

  const indexData = Object.entries(data.indexes).map(
    ([name, { value, change }]) => ({
      name,
      value,
      change,
    })
  );

  const renderIndexTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const { value, change } = payload[0].payload;
      return (
        <div className="rounded border bg-white p-2 text-sm shadow">
          <p className="font-semibold">{label}</p>
          <p>Level: {value.toLocaleString()}</p>
          <p>Change: {change.toFixed(2)}%</p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="container mx-auto p-4">
      <h1 className="mb-4 text-2xl">
        {t('app.modes.market', { defaultValue: 'Market Overview' })}
      </h1>

      <div className="mb-8">
        <h2 className="mb-2 text-xl">
          {t('market.indexLevels', { defaultValue: 'Index Levels' })}
        </h2>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={indexData}>
            <XAxis dataKey="name" />
            <YAxis />
            <Tooltip content={renderIndexTooltip} />
            <Bar dataKey="change">
              {indexData.map((entry) => (
                <Cell
                  key={entry.name}
                  fill={entry.change >= 0 ? '#16a34a' : '#dc2626'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <table className="mt-4 w-full text-left">
          <thead>
            <tr>
              <th>{t('market.index', { defaultValue: 'Index' })}</th>
              <th>{t('market.level', { defaultValue: 'Level' })}</th>
              <th>{t('market.changePct', { defaultValue: '% Change' })}</th>
            </tr>
          </thead>
          <tbody>
            {indexData.map((row) => (
              <tr key={row.name}>
                <td>{row.name}</td>
                <td>{row.value.toLocaleString()}</td>
                <td
                  className={
                    row.change !== undefined && row.change !== null
                      ? row.change >= 0
                        ? 'text-green-600'
                        : 'text-red-600'
                      : undefined
                  }
                >
                  {row.change !== undefined && row.change !== null
                    ? `${row.change.toFixed(2)}%`
                    : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mb-8">
        <h2 className="mb-2 text-xl">
          {t('market.sectorPerformance', {
            defaultValue: 'Sector Performance',
          })}
        </h2>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={data.sectors}>
            <XAxis
              dataKey="sector"
              interval={0}
              angle={-45}
              textAnchor="end"
              height={100}
            />
            <YAxis />
            <Tooltip />
            <Bar dataKey="change" fill="#82ca9d" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div>
        <h2 className="mb-2 text-xl">
          {t('market.latestHeadlines', { defaultValue: 'Latest Headlines' })}
        </h2>
        {data.headlines.length === 0 ? (
          <p>
            {t('market.noHeadlines', {
              defaultValue: 'No headlines available',
            })}
          </p>
        ) : (
          <ul className="list-disc pl-4">
            {data.headlines.map((h, idx) => (
              <li key={idx}>
                <a
                  href={h.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-500 hover:underline"
                >
                  {h.headline}
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
