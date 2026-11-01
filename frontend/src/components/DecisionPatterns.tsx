import { useTranslation } from 'react-i18next';
import type {
  DecisionPatternGroup,
  DecisionPatternRow,
  DecisionPatterns as Patterns,
} from '../types';

function groupKind(group: DecisionPatternGroup): string {
  return group.kind === 'trade' && group.trade_type
    ? `decisionJournal.patternsKind_${group.trade_type}`
    : `decisionJournal.patternsKind_${group.kind}`;
}

function PatternRow({ row }: { row: DecisionPatternRow }) {
  const { t } = useTranslation();
  return (
    <li>
      {t('decisionJournal.patternsRow', {
        alternative: t(
          `decisionJournal.patternsAlternative_${row.alternative}`
        ),
        basis: t(`decisionJournal.patternsBasis_${row.return_basis}`, {
          defaultValue: row.return_basis,
        }),
        above: row.above,
        below: row.below,
        level: row.level,
        comparisons: row.comparisons,
        from: row.first_date,
        to: row.last_date,
      })}
    </li>
  );
}

function PatternGroup({ group }: { group: DecisionPatternGroup }) {
  const { t } = useTranslation();
  return (
    <div className="mt-1 border-l pl-2">
      <p className="text-xs font-medium">
        {t('decisionJournal.patternsGroup', {
          kind: t(groupKind(group)),
          horizon: group.horizon_months,
          trendWatch: t(
            `decisionJournal.patternsTrendWatch_${group.trend_watch}`
          ),
        })}
      </p>
      <ul className="text-xs">
        {group.rows.map((row) => (
          <PatternRow
            key={`${row.alternative}-${row.return_basis}`}
            row={row}
          />
        ))}
      </ul>
      {group.split_by_basis && (
        <p className="text-xs italic">
          {t('decisionJournal.patternsSplitByBasis')}
        </p>
      )}
    </div>
  );
}

const groupKey = (g: DecisionPatternGroup) =>
  `${g.kind}-${g.trade_type ?? ''}-${g.trend_watch}-${g.horizon_months}`;

/**
 * Patterns over time (#10489): counts of how the option taken ended against
 * each kind of alternative, across reviewed decisions. Figures only; a count
 * is listed once enough comparisons stand behind it.
 */
export default function DecisionPatterns({ patterns }: { patterns: Patterns }) {
  const { t } = useTranslation();
  if (patterns.reviewed_entries === 0) return null;
  const counts = {
    min: patterns.min_reviewed,
    reviewed: patterns.reviewed_entries,
  };
  const empty = patterns.groups.length === 0;
  return (
    <section
      className="mb-3 text-sm"
      aria-label={t('decisionJournal.patternsTitle')}
    >
      <h3 className="font-medium">{t('decisionJournal.patternsTitle')}</h3>
      <p className="text-xs text-[var(--surface-muted-color)]">
        {t(
          empty
            ? 'decisionJournal.patternsNone'
            : 'decisionJournal.patternsIntro',
          counts
        )}
      </p>
      {patterns.groups.map((group) => (
        <PatternGroup key={groupKey(group)} group={group} />
      ))}
    </section>
  );
}
