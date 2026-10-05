import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
} from 'recharts';
import { getSectorDetail } from '../../api';
import type { SectorDetail, SectorRegion } from '../../types';

const RETURN_PERIODS = ['1D', '1W', '1M', 'YTD'] as const;

function formatPct(value: number | null | undefined): string {
  return typeof value === 'number' ? `${value.toFixed(2)}%` : '—';
}

function changeClass(value: number | null | undefined): string | undefined {
  if (typeof value !== 'number') return undefined;
  return value >= 0 ? 'text-green-600' : 'text-red-600';
}

function ReturnsRow({ returns }: { returns: SectorDetail['returns'] }) {
  return (
    <dl className="mb-4 grid grid-cols-4 gap-2 text-center">
      {RETURN_PERIODS.map((period) => (
        <div key={period}>
          <dt className="text-xs uppercase text-gray-500">{period}</dt>
          <dd className={changeClass(returns[period])}>
            {formatPct(returns[period])}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function ConstituentsTable({ detail }: { detail: SectorDetail }) {
  const { t } = useTranslation();
  return (
    <table className="w-full text-left">
      <thead>
        <tr>
          <th>{t('market.ticker', { defaultValue: 'Ticker' })}</th>
          <th>{t('market.name', { defaultValue: 'Name' })}</th>
          <th>{t('market.price', { defaultValue: 'Price' })}</th>
          <th>{t('market.changePct', { defaultValue: '% Change' })}</th>
        </tr>
      </thead>
      <tbody>
        {detail.constituents.map((row) => (
          <tr key={row.ticker}>
            <td>{row.ticker}</td>
            <td>{row.name}</td>
            <td>{row.price !== null ? row.price.toLocaleString() : '—'}</td>
            <td className={changeClass(row.change)}>{formatPct(row.change)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function BasisNote({ detail }: { detail: SectorDetail }) {
  const { t } = useTranslation();
  if (detail.proxy) {
    return (
      <p className="mb-2 text-sm text-gray-500">
        {t('market.sectorProxy', {
          defaultValue:
            'Tracked via {{ticker}} ({{name}}). Chart shows its closing price.',
          ticker: detail.proxy.ticker,
          name: detail.proxy.name,
        })}
      </p>
    );
  }
  return (
    <p className="mb-2 text-sm text-gray-500">
      {t('market.sectorBasket', {
        defaultValue:
          'No sector ETF for this market: performance is an equal-weighted basket of the constituents below. Chart is rebased to 100.',
      })}
    </p>
  );
}

function DetailBody({ detail }: { detail: SectorDetail }) {
  const { t } = useTranslation();
  return (
    <>
      <BasisNote detail={detail} />
      <ReturnsRow returns={detail.returns} />
      {detail.history.length > 0 && (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={detail.history}>
            <XAxis dataKey="date" minTickGap={40} />
            <YAxis domain={['auto', 'auto']} />
            <Tooltip
              contentStyle={{ backgroundColor: '#fff', color: '#213547' }}
            />
            <Line
              type="monotone"
              dataKey="value"
              dot={false}
              stroke="#2563eb"
            />
          </LineChart>
        </ResponsiveContainer>
      )}
      <h4 className="mb-1 mt-4 font-semibold">
        {t('market.representativeConstituents', {
          defaultValue:
            'Representative constituents (not full index membership)',
        })}
      </h4>
      <ConstituentsTable detail={detail} />
    </>
  );
}

interface SectorDetailPanelProps {
  region: SectorRegion;
  sector: string;
  onClose: () => void;
}

export default function SectorDetailPanel({
  region,
  sector,
  onClose,
}: SectorDetailPanelProps) {
  const { t } = useTranslation();
  const [detail, setDetail] = useState<SectorDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setDetail(null);
    setError(null);
    getSectorDetail(region, sector, controller.signal)
      .then(setDetail)
      .catch((e) => {
        if (controller.signal.aborted) return;
        setError(e instanceof Error ? e.message : String(e));
      });
    return () => controller.abort();
  }, [region, sector]);

  return (
    <section
      aria-label={t('market.sectorDetail', { defaultValue: 'Sector detail' })}
      className="mt-4 rounded border border-gray-300 p-4"
    >
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-lg font-semibold">{sector}</h3>
        <button type="button" className="text-sm underline" onClick={onClose}>
          {t('common.close', { defaultValue: 'Close' })}
        </button>
      </div>
      {error && <p className="text-red-500">{error}</p>}
      {!error && !detail && <p>{t('common.loading')}</p>}
      {detail && <DetailBody detail={detail} />}
    </section>
  );
}
