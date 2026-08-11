import { useTranslation } from 'react-i18next';
import { RelativeViewToggle } from './RelativeViewToggle';

export type SparkRange = 7 | 30 | 180;

type ViewPreset = {
  label: string;
  value: string;
};

type Props = {
  sparkRange: SparkRange;
  onSparkRangeChange: (range: SparkRange) => void;
  viewPresets: ViewPreset[];
  viewPreset: string;
  onViewPresetChange: (preset: string) => void;
  minimumGain: string;
  onMinimumGainChange: (value: string) => void;
  onSellEligible: () => void;
};

export function HoldingsFilterControls({
  sparkRange,
  onSparkRangeChange,
  viewPresets,
  viewPreset,
  onViewPresetChange,
  minimumGain,
  onMinimumGainChange,
  onSellEligible,
}: Props) {
  const { t } = useTranslation();

  return (
    <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1">
      <RelativeViewToggle />
      <span className="flex items-center gap-1">
        {t('holdingsTable.range')}
        {([7, 30, 180] as const).map((days) => (
          <label key={days} className="ml-1">
            <input
              type="radio"
              name="sparkRange"
              checked={sparkRange === days}
              onChange={() => onSparkRangeChange(days)}
            />
            {t('holdingsTable.rangeOption', { count: days })}
          </label>
        ))}
      </span>
      <span className="flex items-center gap-1">
        {t('holdingsTable.view')}
        {viewPresets.map((preset) => (
          <button
            key={preset.value}
            type="button"
            onClick={() => onViewPresetChange(preset.value)}
            className={`ml-1 ${viewPreset === preset.value ? 'font-bold' : ''} focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500`}
          >
            {preset.label}
          </button>
        ))}
      </span>
      <span className="flex items-center gap-1">
        {t('holdingsTable.quickFilters')}
        <button
          type="button"
          className="ml-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500"
          onClick={onSellEligible}
        >
          {t('holdingsTable.quickFiltersSellEligible')}
        </button>
        <input
          type="number"
          placeholder={t('holdingsTable.minimumGainPrompt')}
          value={minimumGain}
          onChange={(event) => onMinimumGainChange(event.target.value)}
          className="ml-1 w-24"
        />
      </span>
    </div>
  );
}
