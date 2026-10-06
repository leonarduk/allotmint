import { useTranslation } from 'react-i18next';

import type { ReportingCurrency } from '../hooks/useReportingCurrency';

// Full width so it sits on its own line inside a wrapping row of cards.
const NOTE_STYLE = {
  fontSize: '0.85rem',
  flexBasis: '100%',
  margin: 0,
} as const;

/**
 * Says when amounts are not plain GBP: translated into the base currency at
 * today's rate, or left in GBP because there is no rate for it (#9768).
 * Renders nothing while reporting in GBP or waiting for the rate.
 */
export function ReportingCurrencyNote({
  reporting,
}: {
  reporting: ReportingCurrency;
}) {
  const { t } = useTranslation();
  if (reporting.status === 'converted' && reporting.gbpPerUnit !== null) {
    return (
      <p
        className="reporting-currency-note"
        style={{ ...NOTE_STYLE, opacity: 0.8 }}
      >
        {t('reportingCurrency.converted', {
          currency: reporting.currency,
          rate: reporting.gbpPerUnit.toFixed(4),
        })}
      </p>
    );
  }
  if (reporting.status === 'unavailable') {
    return (
      <p className="reporting-currency-note" role="status" style={NOTE_STYLE}>
        {t('reportingCurrency.unavailable', {
          currency: reporting.configuredCurrency,
        })}
      </p>
    );
  }
  return null;
}

export default ReportingCurrencyNote;
