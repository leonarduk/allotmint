import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getMarketOverview } from '../api';
import type { MarketOverview as MarketOverviewData } from '../types';
import EmptyState from '../components/EmptyState';
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

// Shared sign colours (#7817): the index and sector charts must never
// disagree about which way is up.
const POSITIVE_COLOR = '#16a34a';
const NEGATIVE_COLOR = '#dc2626';
const changeColor = (change: number | null | undefined) =>
  (change ?? 0) >= 0 ? POSITIVE_COLOR : NEGATIVE_COLOR;
const SECTOR_ROW_HEIGHT = 36;
const SECTOR_LABEL_WIDTH = 160;
const formatPctTick = (value: unknown) => `${Number(value).toFixed(1)}%`;

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
    getMarketOverview()
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

  const usesUsSectorFallback = data.sectors.some((s) => s.source === 'us_etf');

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

      <div className="mb-8">
        <h2 className="mb-2 text-xl">
          {t('market.sectorChange', { defaultValue: 'Sector % Change' })}
        </h2>
        {usesUsSectorFallback && (
          <p className="mb-2 text-sm text-gray-500">
            {t('market.sectorUsFallback', {
              defaultValue:
                'UK sector data is unavailable; showing US sector ETF performance instead.',
            })}
          </p>
        )}
        {/* Horizontal bars: sector names are long ("Communication Services"),
            and rotated X-axis labels were clipped on desktop and collided at
            phone width (#7817). Category labels on the Y axis stay legible. */}
        {data.sectors.length === 0 ? (
          <EmptyState
            message={t('market.noSectors', {
              defaultValue: 'No sector data available',
            })}
          />
        ) : (
          <ResponsiveContainer
            width="100%"
            height={Math.max(200, data.sectors.length * SECTOR_ROW_HEIGHT + 30)}
          >
            <BarChart
              data={data.sectors}
              layout="vertical"
              margin={{ top: 5, right: 20, bottom: 5, left: 5 }}
            >
              <XAxis
                type="number"
                tickFormatter={formatPctTick}
                height={45}
                label={{
                  value: t('market.changePct', { defaultValue: '% Change' }),
                  position: 'insideBottom',
                  offset: 0,
                }}
              />
              <YAxis
                type="category"
                dataKey="sector"
                interval={0}
                width={SECTOR_LABEL_WIDTH}
                tick={{ fontSize: 12 }}
              />
              <Tooltip
                contentStyle={{ backgroundColor: '#fff', color: '#213547' }}
                formatter={(value) => [
                  `${Number(value).toFixed(2)}%`,
                  t('market.changePct', { defaultValue: '% Change' }),
                ]}
              />
              <Bar dataKey="change">
                {data.sectors.map((entry) => (
                  <Cell key={entry.sector} fill={changeColor(entry.change)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

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
