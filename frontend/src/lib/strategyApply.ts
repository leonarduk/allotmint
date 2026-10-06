import type { TFunction } from 'i18next';
import type { StrategyList } from '../types';

/**
 * Ask before applying a strategy over targets that are custom or modified
 * since the last apply; true when the apply should go ahead.
 */
export function confirmApply(
  data: StrategyList,
  hasTargets: boolean,
  name: string,
  t: TFunction
): boolean {
  const replacesCustomTargets =
    hasTargets && (data.active == null || data.active.modified);
  return (
    !replacesCustomTargets ||
    window.confirm(t('strategyLibrary.confirmReplace', { name }))
  );
}
