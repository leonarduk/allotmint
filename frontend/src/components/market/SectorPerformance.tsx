import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
} from 'recharts';
import { getMarketSectors } from '../../api';
import type { RegionSectors, SectorRegion } from '../../types';
import SectorDetailPanel from './SectorDetailPanel';

const REGION_OPTIONS: { key: SectorRegion; label: string }[] = [
  { key: 'global', label: 'Global' },
  { key: 'us', label: 'US' },
  { key: 'uk', label: 'UK' },
];

const BAR_FILL = '#82ca9d';
const SELECTED_FILL = '#2f855a';

interface RegionToggleProps {
  active: SectorRegion | undefined;
  onSelect: (region: SectorRegion) => void;
}

function RegionToggle({ active, onSelect }: RegionToggleProps) {
  const { t } = useTranslation();
  return (
    <div
      role="group"
      aria-label={t('market.sectorRegion', { defaultValue: 'Sector region' })}
      className="inline-flex overflow-hidden rounded border border-gray-400"
    >
      {REGION_OPTIONS.map(({ key, label }) => (
        <button
          key={key}
          type="button"
          aria-pressed={active === key}
          onClick={() => onSelect(key)}
          className={`px-3 py-1 text-sm ${active === key ? 'bg-gray-600 text-white' : ''}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

interface SectorChartProps {
  data: RegionSectors;
  selected: string | null;
  onSelect: (sector: string) => void;
}

function SectorChart({ data, selected, onSelect }: SectorChartProps) {
  return (
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
        <Tooltip contentStyle={{ backgroundColor: '#fff', color: '#213547' }} />
        <Bar
          dataKey="change"
          cursor="pointer"
          onClick={(entry: {
            sector?: string;
            payload?: { sector?: string };
          }) => {
            const sector = entry.sector ?? entry.payload?.sector;
            if (sector) onSelect(sector);
          }}
        >
          {data.sectors.map((row) => (
            <Cell
              key={row.sector}
              fill={row.sector === selected ? SELECTED_FILL : BAR_FILL}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Keyboard-accessible sector list mirroring the chart's bars. */
function SectorButtons({ data, selected, onSelect }: SectorChartProps) {
  return (
    <ul className="mt-2 flex flex-wrap gap-2 text-sm">
      {data.sectors.map((row) => (
        <li key={row.sector}>
          <button
            type="button"
            aria-pressed={row.sector === selected}
            onClick={() => onSelect(row.sector)}
            className="rounded border border-gray-400 px-2 py-0.5"
          >
            {row.sector}{' '}
            <span
              className={row.change >= 0 ? 'text-green-600' : 'text-red-600'}
            >
              {row.change.toFixed(2)}%
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export default function SectorPerformance() {
  const { t } = useTranslation();
  // undefined = let the backend pick its configured default region.
  const [requested, setRequested] = useState<SectorRegion | undefined>(
    undefined
  );
  const [data, setData] = useState<RegionSectors | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    setSelected(null);
    getMarketSectors(requested, controller.signal)
      .then(setData)
      .catch((e) => {
        if (controller.signal.aborted) return;
        setError(e instanceof Error ? e.message : String(e));
      });
    return () => controller.abort();
  }, [requested]);

  const activeRegion = requested ?? data?.region;
  return (
    <div className="mb-8">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl">
          {t('market.sectorPerformance', {
            defaultValue: 'Sector Performance',
          })}
        </h2>
        <RegionToggle active={activeRegion} onSelect={setRequested} />
      </div>
      {error && <p className="text-red-500">{error}</p>}
      {!error && !data && <p>{t('common.loading')}</p>}
      {!error && data && (
        <>
          <SectorChart data={data} selected={selected} onSelect={setSelected} />
          <SectorButtons
            data={data}
            selected={selected}
            onSelect={setSelected}
          />
          {selected && (
            <SectorDetailPanel
              region={data.region}
              sector={selected}
              onClose={() => setSelected(null)}
            />
          )}
        </>
      )}
    </div>
  );
}
