import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getMarketOverview } from '../api';
import type { MarketOverview as MarketOverviewData } from '../types';
import EmptyState from '../components/EmptyState';
import SectorPerformance from '../components/market/SectorPerformance';
import { changeColor, formatPctTick } from '../components/market/chartFormat';
import { formatPublishedAt } from '../lib/date';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
} from 'recharts';

export const IndexTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    const { value, change } = payload[0].payload;
    const safeChange = typeof change === 'number' ? change : 0;
    return (
      <div className="rounded border bg-white p-2 text-sm shadow text-gray-900">
        <p className="font-semibold">{label}</p>
        <p>Level: {value.toLocaleString()}</p>
        <p>Change: {safeChange.toFixed(2)}%</p>
      </div>
    );
  }
  return null;
};

export default function MarketOverview() {
  const { t } = useTranslation();
  const [data, setData] = useState<MarketOverviewData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Sectors are loaded per region by <SectorPerformance />.
    getMarketOverview({ includeSectors: false })
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  const pageHeading = t('app.modes.market', { defaultValue: 'Market Overview' });
  if (loading) {
    return (
      <div className="container mx-auto p-4">
        <h1 className="mb-4 text-2xl">{pageHeading}</h1>
        <p>{t('common.loading')}</p>
      </div>
    );
  }
  if (error) {
    return (
      <div className="container mx-auto p-4">
        <h1 className="mb-4 text-2xl">{pageHeading}</h1>
        <p className="text-red-500">{error}</p>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="container mx-auto p-4">
        <h1 className="mb-4 text-2xl">{pageHeading}</h1>
      </div>
    );
  }

  const indexData = Object.entries(data.indexes).map(
    ([name, { value, change }]) => ({
      name,
      value,
      change,
    })
  );

  return (
    <div className="container mx-auto p-4">
      <h1 className="mb-4 text-2xl">{pageHeading}</h1>

      <div className="mb-8">
        {/* The bars plot % change, not raw level (#7106) -- heading must say
            so, or this is #2541's mislabelled axis all over again. The raw
            levels are still available in the table below. */}
        <h2 className="mb-2 text-xl">
          {t('market.indexChange', { defaultValue: 'Index % Change' })}
        </h2>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={indexData}>
            <XAxis dataKey="name" />
            <YAxis tickFormatter={formatPctTick} />
            <Tooltip content={<IndexTooltip />} />
            <Bar dataKey="change">
              {indexData.map((entry) => (
                <Cell key={entry.name} fill={changeColor(entry.change)} />
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

      <SectorPerformance />

      <div>
        <h2 className="mb-2 text-xl">
          {t('market.latestHeadlines', { defaultValue: 'Latest Headlines' })}
        </h2>
        {data.headlines.length === 0 ? (
          <EmptyState
            message={t('market.noHeadlines', { defaultValue: 'No headlines available' })}
          />
        ) : (
          <ul className="list-disc pl-4">
            {data.headlines.map((h, idx) => {
              const age = formatPublishedAt(h.published_at);
              return (
                <li key={idx}>
                  <a
                    href={h.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-500 hover:underline"
                  >
                    {h.headline}
                  </a>
                  {age && (
                    <span
                      className="ml-2 text-sm text-gray-500"
                      title={h.published_at ?? undefined}
                    >
                      — {age}
                    </span>
                  )}
                  {h.stale && (
                    <span
                      className="ml-2 rounded bg-yellow-100 px-1.5 py-0.5 text-xs font-medium text-yellow-800"
                      title={t('market.staleHeadlineTooltip', {
                        defaultValue:
                          'This headline is from a cache that has not refreshed recently; live news fetches may be failing or rate-limited.',
                      })}
                    >
                      {t('market.staleHeadline', { defaultValue: 'Stale' })}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
