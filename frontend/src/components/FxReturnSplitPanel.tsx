import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getInstrumentFxSplit } from '../api';
import { signedPercent } from '../lib/money';
import type { FxReturnSplit } from '../types';

type Props = {
  ticker: string;
  /** The page's selected range in calendar days (0 = all history). */
  days: number;
  mutedColor: string;
  positiveColor: string;
  negativeColor: string;
};

const COMPONENTS = [
  { key: 'local_return', label: 'instrumentDetail.fxSplit.local' },
  { key: 'fx_return', label: 'instrumentDetail.fxSplit.fx' },
  { key: 'cross_term', label: 'instrumentDetail.fxSplit.cross' },
  { key: 'gbp_return', label: 'instrumentDetail.fxSplit.gbp' },
] as const;

/**
 * Local vs FX split of a non-sterling instrument's GBP price return over the
 * page's selected range (#9776). Renders nothing for GBP/GBX instruments
 * (``applicable: false``). When the backend has no split (a missing FX rate,
 * too little price history) it shows the reason instead of numbers.
 */
export function FxReturnSplitPanel({
  ticker,
  days,
  mutedColor,
  positiveColor,
  negativeColor,
}: Props) {
  const { t } = useTranslation();
  const [split, setSplit] = useState<FxReturnSplit | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setSplit(null);
    setFailed(false);
    getInstrumentFxSplit(ticker, days, controller.signal)
      .then(setSplit)
      .catch((e: unknown) => {
        if (controller.signal.aborted) return;
        console.warn('FX return split unavailable for', ticker, e);
        setFailed(true);
      });
    return () => controller.abort();
  }, [ticker, days]);

  if (failed) {
    return (
      <p
        data-testid="fx-split-error"
        style={{ fontSize: '0.85rem', color: mutedColor }}
      >
        {t('instrumentDetail.fxSplit.unavailable')}
      </p>
    );
  }
  if (!split || !split.applicable) return null;

  const vars = {
    currency: split.currency,
    start: split.start ?? '',
    end: split.end ?? '',
  };
  return (
    <section
      data-testid="fx-split-panel"
      style={{ margin: '1rem 0', fontSize: '0.85rem' }}
    >
      <h3 style={{ marginBottom: '0.25rem' }}>
        {t('instrumentDetail.fxSplit.title')}
      </h3>
      <div style={{ color: mutedColor, marginBottom: '0.25rem' }}>
        {split.start && split.end
          ? t('instrumentDetail.fxSplit.basisWithDates', vars)
          : t('instrumentDetail.fxSplit.basis')}
      </div>
      {split.reason ? (
        <p
          data-testid="fx-split-reason"
          style={{ color: mutedColor, margin: 0 }}
        >
          {t(`instrumentDetail.fxSplit.reasons.${split.reason}`, vars)}
        </p>
      ) : (
        <table>
          <tbody>
            {COMPONENTS.map(({ key, label }) => {
              const value = split[key] ?? NaN;
              const colour =
                value > 0
                  ? positiveColor
                  : value < 0
                    ? negativeColor
                    : undefined;
              const isTotal = key === 'gbp_return';
              return (
                <tr key={key} data-testid={`fx-split-${key}`}>
                  <th
                    scope="row"
                    style={{
                      textAlign: 'left',
                      fontWeight: isTotal ? 600 : 400,
                      paddingRight: '1rem',
                    }}
                  >
                    {t(label, vars)}
                  </th>
                  <td
                    style={{
                      textAlign: 'right',
                      color: colour,
                      fontWeight: isTotal ? 600 : 400,
                    }}
                  >
                    {Number.isFinite(value) ? signedPercent(value) : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
