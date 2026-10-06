import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import PriceTriggersPanel from './PriceTriggersPanel';
import { useAlertIdentity } from '../hooks/useAlertIdentity';
import { useDemoReadOnly } from '../hooks/useDemoReadOnly';

interface Props {
  /**
   * Full ticker the alerts watch, in price-snapshot form (e.g. "VOD.L").
   * Empty when the exchange is unknown: no alert can be matched then.
   */
  ticker: string;
  /** Latest GBP close, shown as a reference when picking a level. */
  latestPrice?: number | null;
  /** Reports how many alerts this instrument has after each (re)load. */
  onCountChange?: (count: number) => void;
}

/**
 * Add/edit/remove price alerts for a single instrument, in place on the
 * research page. Alerts are stored per resolved identity (see
 * useAlertIdentity), the same store the Alert Settings page manages.
 */
export default function InstrumentAlertsSection({
  ticker,
  latestPrice,
  onCountChange,
}: Props) {
  const { t } = useTranslation();
  const { identity, resolving } = useAlertIdentity();
  const { demoReadOnly, reason } = useDemoReadOnly();

  if (!ticker) {
    return (
      <p style={{ marginBottom: '1rem' }}>
        {t('alertSettings.triggers.exchangeUnknown')}
      </p>
    );
  }
  if (resolving) return null;
  if (!identity) {
    return (
      <p style={{ marginBottom: '1rem' }}>
        {t('alertSettings.signInNotice')}{' '}
        <Link to="/alert-settings">
          {t('alertSettings.triggers.manageAll')}
        </Link>
      </p>
    );
  }

  return (
    <div style={{ marginBottom: '1rem' }}>
      <PriceTriggersPanel
        identity={identity}
        disabled={demoReadOnly}
        disabledReason={reason()}
        ticker={ticker}
        latestPrice={latestPrice}
        onTriggersLoaded={(rows) => onCountChange?.(rows.length)}
      />
      <p style={{ fontSize: '0.85em' }}>
        <Link to="/alert-settings">
          {t('alertSettings.triggers.manageAll')}
        </Link>
      </p>
    </div>
  );
}
