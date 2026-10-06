import { useTranslation } from 'react-i18next';
import type { MarketPeriod } from '../../types';

export const PERIOD_OPTIONS: { key: MarketPeriod; label: string }[] = [
  { key: '1D', label: '1 day' },
  { key: '1W', label: '1 week' },
  { key: '1M', label: '30 days' },
  { key: '3M', label: '90 days' },
  { key: '1Y', label: '1 year' },
];

/** Translated label for `period`, e.g. "30 days". */
export function usePeriodLabel(period: MarketPeriod): string {
  const { t } = useTranslation();
  const option = PERIOD_OPTIONS.find(({ key }) => key === period);
  return t(`market.period.${period}`, {
    defaultValue: option?.label ?? period,
  });
}
