import { useTranslation } from 'react-i18next';
import type { MarketPeriod } from '../../types';
import { PERIOD_OPTIONS } from './periods';

interface PeriodToggleProps {
  value: MarketPeriod;
  onChange: (period: MarketPeriod) => void;
}

/** Radio group choosing the change window for the index and sector charts. */
export default function PeriodToggle({ value, onChange }: PeriodToggleProps) {
  const { t } = useTranslation();
  return (
    <fieldset className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1">
      <legend className="mb-1 text-sm font-semibold">
        {t('market.changePeriod', { defaultValue: 'Change over' })}
      </legend>
      {PERIOD_OPTIONS.map(({ key, label }) => (
        <label key={key} className="inline-flex items-center gap-1 text-sm">
          <input
            type="radio"
            name="market-period"
            value={key}
            checked={value === key}
            onChange={() => onChange(key)}
          />
          {t(`market.period.${key}`, { defaultValue: label })}
        </label>
      ))}
    </fieldset>
  );
}
