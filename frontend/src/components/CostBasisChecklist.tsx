import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { Account } from '../types';
import { percent } from '../lib/money';
import { COST_BASIS_BOOK_SUSPECT } from '../lib/costBasis';
import {
  buildCostBasisChecklist,
  costBasisFillHref,
  topValueShare,
} from '../lib/costBasisChecklist';
import { useReportingCurrency } from '../hooks/useReportingCurrency';
import tableStyles from '../styles/table.module.css';

/** Rows shown before "Show all": enough to recover most of the value (#7825). */
export const CHECKLIST_TOP_COUNT = 10;

type Props = {
  accounts: Account[];
};

/**
 * Actionable companion to the dashboard's "Excludes N holdings with no
 * reliable cost basis" note (#7825): the excluded holdings, largest market
 * value first, each linking to the set-holding form prefilled for it.
 */
export function CostBasisChecklist({ accounts }: Props) {
  const { t } = useTranslation();
  const reporting = useReportingCurrency();
  const [showAll, setShowAll] = useState(false);
  const gaps = useMemo(() => buildCostBasisChecklist(accounts), [accounts]);

  if (gaps.length === 0) return null;

  const visible = showAll ? gaps : gaps.slice(0, CHECKLIST_TOP_COUNT);
  const topCount = Math.min(CHECKLIST_TOP_COUNT, gaps.length);
  const share = topValueShare(gaps, topCount);

  return (
    <details
      data-testid="cost-basis-checklist"
      style={{
        margin: '0 0 1rem',
        padding: '0.75rem 1rem',
        backgroundColor: 'var(--summary-card-bg)',
        border: '1px solid var(--summary-card-border)',
        borderRadius: '6px',
      }}
    >
      <summary style={{ cursor: 'pointer', fontWeight: 600 }}>
        {t('costBasisChecklist.summary', { count: gaps.length })}
      </summary>
      <p style={{ fontSize: '0.85rem', color: 'var(--summary-card-label)' }}>
        {t('costBasisChecklist.intro', {
          top: topCount,
          share: percent(share * 100, 0),
        })}
      </p>
      <table className={tableStyles.table}>
        <thead>
          <tr>
            <th className={tableStyles.cell}>
              {t('costBasisChecklist.holding')}
            </th>
            <th className={tableStyles.cell}>
              {t('costBasisChecklist.account')}
            </th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>
              {t('costBasisChecklist.value')}
            </th>
            <th className={tableStyles.cell}>
              {t('costBasisChecklist.problem')}
            </th>
            <th className={tableStyles.cell} />
          </tr>
        </thead>
        <tbody>
          {visible.map((gap) => (
            <tr key={`${gap.owner}/${gap.account}/${gap.ticker}`}>
              <td className={tableStyles.cell}>
                <strong>{gap.ticker}</strong>
                {gap.name !== gap.ticker && ` ${gap.name}`}
              </td>
              <td className={tableStyles.cell}>
                {gap.owner ? `${gap.owner} · ${gap.account}` : gap.account}
              </td>
              <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                {gap.marketValue === null
                  ? '—'
                  : reporting.format(gap.marketValue)}
              </td>
              <td className={tableStyles.cell}>
                {gap.source === COST_BASIS_BOOK_SUSPECT
                  ? t('costBasisChecklist.suspect')
                  : t('costBasisChecklist.missing')}
              </td>
              <td className={tableStyles.cell}>
                <Link to={costBasisFillHref(gap)}>
                  {t('costBasisChecklist.addCost')}
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {gaps.length > CHECKLIST_TOP_COUNT && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          style={{ marginTop: '0.5rem' }}
        >
          {showAll
            ? t('costBasisChecklist.showTop', { count: CHECKLIST_TOP_COUNT })
            : t('costBasisChecklist.showAll', { count: gaps.length })}
        </button>
      )}
    </details>
  );
}

export default CostBasisChecklist;
