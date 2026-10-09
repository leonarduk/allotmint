import { useTranslation } from 'react-i18next';
import { Receipt } from 'lucide-react';
import { percent } from '../lib/money';
import type { FundChargeTotals } from '../lib/fundCharges';
import type { AllInCostPart } from '../types';
import { useReportingCurrency } from '../hooks/useReportingCurrency';

type Props = {
  charges: FundChargeTotals;
  /** All-in annual cost for the shown scope (#10482); omitted while loading or unavailable. */
  allInCost?: AllInCostPart | null;
  /** Per-account rows of the same all-in cost, listed when there is more than one. */
  allInAccounts?: AllInCostPart[];
};

const labelStyle = { fontSize: '0.9rem', color: 'var(--summary-card-label)' };
const valueStyle = { fontSize: '1.2rem', fontWeight: 'bold' } as const;
const noteStyle = { fontSize: '0.8rem', color: 'var(--summary-card-label)' };

/**
 * True when no part of the cost is known: every holding lacks a charge and no
 * fees were paid. ``known_cost_gbp`` is then 0 only because nothing was
 * counted, so it is shown as unknown rather than as GBP 0 (#10482).
 */
function nothingKnown(part: AllInCostPart): boolean {
  return (
    part.fund_charges_gbp === null &&
    part.dealing_fees_gbp + part.account_charges_gbp === 0
  );
}

function CostFigure({ part }: { part: AllInCostPart }) {
  const { t } = useTranslation();
  const reporting = useReportingCurrency();
  if (nothingKnown(part)) return <>{t('fundCharges.unknown')}</>;
  return (
    <>
      {reporting.format(part.known_cost_gbp)}
      {part.known_cost_pct !== null && ` (${percent(part.known_cost_pct)})`}
      {!part.complete && ` - ${t('fundCharges.partial')}`}
    </>
  );
}

function AllInCostBlock({
  part,
  accounts,
}: {
  part: AllInCostPart;
  accounts: AllInCostPart[];
}) {
  const { t } = useTranslation();
  const reporting = useReportingCurrency();
  const fees = part.dealing_fees_gbp + part.account_charges_gbp;
  const missing: string[] = [];
  if (part.unknown_count > 0)
    missing.push(
      t('fundCharges.allInUnknownValue', {
        value: reporting.format(part.unknown_value_gbp),
        holdings: part.unknown_count,
      })
    );
  if (part.trades_without_fee_data > 0)
    missing.push(
      t('fundCharges.allInUnknownTrades', {
        trades: part.trades_without_fee_data,
      })
    );

  return (
    <div data-testid="fund-charges-all-in">
      <div style={labelStyle}>{t('fundCharges.allInCost')}</div>
      <div style={valueStyle} data-testid="fund-charges-all-in-value">
        <CostFigure part={part} />
      </div>
      <div style={noteStyle}>
        {t('fundCharges.allInBreakdown', {
          funds:
            part.fund_charges_gbp === null
              ? t('fundCharges.unknown')
              : reporting.format(part.fund_charges_gbp),
          fees: reporting.format(fees),
        })}
      </div>
      {missing.length > 0 && (
        <div style={noteStyle} data-testid="fund-charges-all-in-unknown">
          {t('fundCharges.allInNotIncluded', { items: missing.join('; ') })}
        </div>
      )}
      {accounts.length > 1 && (
        <details style={noteStyle}>
          <summary>{t('fundCharges.perAccount')}</summary>
          <ul data-testid="fund-charges-all-in-accounts">
            {accounts.map((row) => (
              <li key={`${row.owner ?? ''}:${row.account ?? ''}`}>
                {[row.owner, row.account].filter(Boolean).join(' ')}:{' '}
                <CostFigure part={row} />
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

/** Weighted fund ongoing charge, estimated annual cost (#7834) and all-in cost (#10482). */
export function FundChargesSummary({
  charges,
  allInCost,
  allInAccounts = [],
}: Props) {
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
        <div style={labelStyle}>{t('fundCharges.weightedCharge')}</div>
        <div style={valueStyle} data-testid="fund-charges-weighted">
          {weightedChargePct === null ? unknown : percent(weightedChargePct)}
        </div>
      </div>
      <div>
        <div style={labelStyle}>{t('fundCharges.annualCost')}</div>
        <div style={valueStyle} data-testid="fund-charges-annual">
          {annualCostGbp === null ? unknown : reporting.format(annualCostGbp)}
        </div>
      </div>
      {note && <div style={noteStyle}>{note}</div>}
      {allInCost && (
        <AllInCostBlock part={allInCost} accounts={allInAccounts} />
      )}
    </div>
  );
}

export default FundChargesSummary;
