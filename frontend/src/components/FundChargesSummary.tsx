import { useTranslation } from 'react-i18next';
import { Receipt } from 'lucide-react';
import { percent } from '../lib/money';
import type { FundChargeTotals } from '../lib/fundCharges';
import { useReportingCurrency } from '../hooks/useReportingCurrency';

type Props = {
  charges: FundChargeTotals;
};

/** Weighted fund ongoing charge and estimated annual cost (#7834). */
export function FundChargesSummary({ charges }: Props) {
  const { t } = useTranslation();
  const reporting = useReportingCurrency();
  const { weightedChargePct, annualCostGbp, holdingCount, unknownCount } =
    charges;
  if (holdingCount === 0) return null;

  const unknown = t('fundCharges.unknown');
  const note =
    unknownCount > 0
      ? t('fundCharges.excludesUnknown', {
          unknown: unknownCount,
          total: holdingCount,
        })
      : undefined;

  return (
    <div
      className="flex-wrap-row"
      data-testid="fund-charges-summary"
      style={{
        gap: '2rem',
        marginBottom: '1rem',
        padding: '0.75rem 1rem',
        backgroundColor: 'var(--summary-card-bg)',
        border: '1px solid var(--summary-card-border)',
        borderRadius: '6px',
        alignItems: 'center',
      }}
    >
      <Receipt size={16} />
      <div>
        <div style={{ fontSize: '0.9rem', color: 'var(--summary-card-label)' }}>
          {t('fundCharges.weightedCharge')}
        </div>
        <div
          style={{ fontSize: '1.2rem', fontWeight: 'bold' }}
          data-testid="fund-charges-weighted"
        >
          {weightedChargePct === null ? unknown : percent(weightedChargePct)}
        </div>
      </div>
      <div>
        <div style={{ fontSize: '0.9rem', color: 'var(--summary-card-label)' }}>
          {t('fundCharges.annualCost')}
        </div>
        <div
          style={{ fontSize: '1.2rem', fontWeight: 'bold' }}
          data-testid="fund-charges-annual"
        >
          {annualCostGbp === null ? unknown : reporting.format(annualCostGbp)}
        </div>
      </div>
      {note && (
        <div style={{ fontSize: '0.8rem', color: 'var(--summary-card-label)' }}>
          {note}
        </div>
      )}
    </div>
  );
}

export default FundChargesSummary;
