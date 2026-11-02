import { useTranslation } from 'react-i18next';
import { isCostBasisEstimate } from '../lib/costBasis';
import tableStyles from '../styles/table.module.css';

type Props = {
  /** The holding's cost_basis_source; the mark renders only for "estimate". */
  source?: string | null;
  /** The day the estimate was taken from the market price. */
  date?: string | null;
  /**
   * For a total instead of one holding: how many of the holdings summed into
   * it have an estimated cost. The mark renders only when it is above 0.
   */
  count?: number;
};

/**
 * Marks a cost or gain figure that rests on an estimated cost (#10095): the
 * user chose "use current price as cost", so the cost is the market price on
 * `date`, not a purchase price, and gain is measured from that day.
 */
export function CostEstimateMark({ source, date, count }: Props) {
  const { t } = useTranslation();
  const shown = count === undefined ? isCostBasisEstimate(source) : count > 0;
  if (!shown) return null;
  const title =
    count !== undefined
      ? t('costBasisChecklist.estimateIncluded', { count })
      : date
        ? t('costBasisChecklist.estimateTitle', { date })
        : t('costBasisChecklist.estimateTitleNoDate');
  return (
    <span
      className={tableStyles.badge}
      title={title}
      aria-label={title}
      data-testid="cost-estimate-mark"
    >
      {t('costBasisChecklist.estimateBadge')}
    </span>
  );
}

export default CostEstimateMark;
