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
import type { MarketPeriod, RegionSectors, SectorRegion } from '../../types';
import EmptyState from '../EmptyState';
import SectorDetailPanel from './SectorDetailPanel';
import { changeColor, formatPctTick } from './chartFormat';

const REGION_OPTIONS: { key: SectorRegion; label: string }[] = [
  { key: 'global', label: 'Global' },
  { key: 'us', label: 'US' },
  { key: 'uk', label: 'UK' },
];

const SECTOR_ROW_HEIGHT = 36;
const SECTOR_LABEL_WIDTH = 160;
// Bars keep their sign colour (#7817); the selected one gets an outline.
const SELECTED_STROKE = '#1f2937';

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
  const { t } = useTranslation();
  const pctLabel = t('market.changePct', { defaultValue: '% Change' });
  // Horizontal bars: sector names are long ("Communication Services"), and
  // rotated X-axis labels were clipped on desktop and collided at phone
  // width (#7817). Category labels on the Y axis stay legible.
  return (
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
          label={{ value: pctLabel, position: 'insideBottom', offset: 0 }}
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
          formatter={(value) => [`${Number(value).toFixed(2)}%`, pctLabel]}
        />
        <Bar
          dataKey="change"
          cursor="pointer"
          // Recharts v3 passes the bar item (row under `payload`) and its
          // index; fall back to the index so a payload shape change can't
          // silently break selection.
          onClick={(
            entry: { payload?: { sector?: string } },
            index: number
          ) => {
            const sector =
              entry?.payload?.sector ?? data.sectors[index]?.sector;
            if (sector) onSelect(sector);
          }}
        >
          {data.sectors.map((row) => (
            <Cell
              key={row.sector}
              fill={changeColor(row.change)}
              stroke={row.sector === selected ? SELECTED_STROKE : undefined}
              strokeWidth={row.sector === selected ? 2 : 0}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function SectorBody({ data, selected, onSelect }: SectorChartProps) {
  const { t } = useTranslation();
  if (data.sectors.length === 0) {
    return (
      <EmptyState
        message={t('market.noSectors', {
          defaultValue: 'No sector data available',
        })}
      />
    );
  }
  const usesBasket = data.sectors.some((row) => row.source === 'basket');
  return (
    <>
      {usesBasket && (
        <p className="mb-2 text-sm text-gray-500">
          {t('market.sectorBasketNote', {
            defaultValue:
              'Sector moves are equal-weighted baskets of representative large constituents.',
          })}
        </p>
      )}
      <SectorChart data={data} selected={selected} onSelect={onSelect} />
      <SectorButtons data={data} selected={selected} onSelect={onSelect} />
    </>
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

interface SectorPerformanceProps {
  period: MarketPeriod;
  /** Translated period label shown in the heading, e.g. "30 days". */
  periodLabel: string;
}

export default function SectorPerformance({
  period,
  periodLabel,
}: SectorPerformanceProps) {
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
    // Drop the previous region's/period's bars so they aren't shown under the
    // new toggle while the fetch is in flight.
    setData(null);
    getMarketSectors(requested, controller.signal, period)
      .then(setData)
      .catch((e) => {
        if (controller.signal.aborted) return;
        setError(e instanceof Error ? e.message : String(e));
      });
    return () => controller.abort();
  }, [requested, period]);

  // The drill-down is per region, so a region switch closes it; a period
  // switch only changes the bars, so the open detail panel stays.
  const selectRegion = (region: SectorRegion) => {
    setSelected(null);
    setRequested(region);
  };

  const activeRegion = requested ?? data?.region;
  return (
    <div className="mb-8">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl">
          {`${t('market.sectorChange', { defaultValue: 'Sector % Change' })} (${periodLabel})`}
        </h2>
        <RegionToggle active={activeRegion} onSelect={selectRegion} />
      </div>
      {error && <p className="text-red-500">{error}</p>}
      {!error && !data && <p>{t('common.loading')}</p>}
      {!error && data && (
        <>
          <SectorBody data={data} selected={selected} onSelect={setSelected} />
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
