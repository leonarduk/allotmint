import { useTranslation } from 'react-i18next';
import InfoTip from './InfoTip';
import styles from './SignalDetails.module.css';

/**
 * Shared presentation for a Buy/Sell signal's strength and skipped checks,
 * used by both the Trading page and the Movers signal table so the two
 * surfaces frame the same signal the same way (#7217).
 */

export function SignalStrength({ confidence }: { confidence?: number | null }) {
  const { t } = useTranslation();
  if (confidence == null) {
    return <>—</>;
  }

  // The backend caps confidence at 1.0 once a signal is far enough past its
  // threshold (backend/agent/trading_agent.py), so "100%" says nothing beyond
  // "capped". Name what it measures instead of showing a meaningless percent.
  if (confidence >= 1) {
    return (
      <>
        {t('trading.strength.saturated', 'Strong (well past threshold)')}
      </>
    );
  }

  const percent = Math.round(confidence * 100);
  let label = t('trading.strength.weak', 'Weak');
  if (confidence >= 0.75) {
    label = t('trading.strength.strong', 'Strong');
  } else if (confidence >= 0.5) {
    label = t('trading.strength.moderate', 'Moderate');
  }

  return <>{t('trading.strength.label', '{{label}} ({{percent}}%)', { label, percent })}</>;
}

/**
 * The per-indicator detail behind a signal (e.g. "The price dropped 7.30% in
 * the last 7 days, ..."). Each factor names the window it was measured over,
 * which is what lets Movers and Trading agree for the same ticker even when
 * the Movers period differs from the signal's lookback (#7217).
 */
export function SignalFactors({
  factors,
  rationale,
}: {
  factors?: string[];
  rationale?: string | null;
}) {
  if (factors && factors.length) {
    return (
      <ul className={styles.factors}>
        {factors.map((factor, idx) => (
          <li key={idx}>{factor}</li>
        ))}
      </ul>
    );
  }
  if (rationale) {
    return <span>{rationale}</span>;
  }
  return <>—</>;
}

export function ChecksSkippedBadge({ checksSkipped }: { checksSkipped?: string[] }) {
  const { t } = useTranslation();
  if (!checksSkipped || !checksSkipped.length) {
    return null;
  }

  // A skipped compliance check is the one a user most needs to see, so it
  // gets its own warning badge rather than sharing the neutral one.
  const complianceSkipped = checksSkipped.includes('compliance');
  const otherChecks = checksSkipped.filter((check) => check !== 'compliance');

  return (
    <span className={styles.checksSkipped}>
      {complianceSkipped && (
        <span className={`${styles.badge} ${styles.warning}`}>
          {t('trading.complianceSkippedBadge', 'Compliance not checked')}
        </span>
      )}
      {otherChecks.length > 0 && (
        <span className={styles.badge}>
          {t('trading.checksSkippedTitle', 'Skipped checks: {{checks}}', {
            checks: otherChecks.join(', '),
          })}
        </span>
      )}
      <InfoTip
        label={t('trading.checksSkippedInfoLabel', "What does 'Checks skipped' mean?")}
        to="/metrics-explained#checks-skipped"
      >
        {t(
          'trading.checksSkippedInfo',
          "An optional check that needs the allotmint-pro add-on could not run. “compliance” means the trade was not checked against your compliance rules; “fundamental_screen” means the P/E and debt/equity filters above (whichever are configured) were not applied to this buy candidate."
        )}
      </InfoTip>
    </span>
  );
}
