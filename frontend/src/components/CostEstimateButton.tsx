import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { estimateCostBasis } from '../api';
import type { CostBasisGap } from '../lib/costBasisChecklist';

type Props = {
  gap: CostBasisGap;
  /** Called after the estimate was recorded, so the portfolio can reload. */
  onEstimated?: () => void;
};

/**
 * The "use current price as cost" fallback on a cost-basis checklist row
 * (#10095). It takes two clicks: the first explains that today's price is
 * recorded as an *estimated* cost, not a purchase price; the second records it.
 */
export function CostEstimateButton({ gap, onEstimated }: Props) {
  const { t } = useTranslation();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const record = async () => {
    setBusy(true);
    setError(null);
    try {
      await estimateCostBasis(gap.owner, gap.account, gap.ticker);
      setConfirming(false);
      onEstimated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  if (!confirming) {
    return (
      <button
        type="button"
        onClick={() => setConfirming(true)}
        title={t('costBasisChecklist.useCurrentPriceHelp')}
      >
        {t('costBasisChecklist.useCurrentPrice')}
      </button>
    );
  }
  return (
    <span role="group" aria-label={t('costBasisChecklist.useCurrentPrice')}>
      <span style={{ fontSize: '0.85rem' }}>
        {t('costBasisChecklist.useCurrentPriceConfirm', { ticker: gap.ticker })}
      </span>{' '}
      <button type="button" disabled={busy} onClick={() => void record()}>
        {t('costBasisChecklist.recordEstimate')}
      </button>{' '}
      <button
        type="button"
        disabled={busy}
        onClick={() => setConfirming(false)}
      >
        {t('costBasisChecklist.cancelEstimate')}
      </button>
      {error && (
        <span role="alert" style={{ display: 'block' }}>
          {t('costBasisChecklist.estimateFailed', { message: error })}
        </span>
      )}
    </span>
  );
}

export default CostEstimateButton;
