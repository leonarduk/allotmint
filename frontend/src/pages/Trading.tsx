import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getTradingSignals } from '../api';
import type { TradingSignal } from '../types';
import { InstrumentDetail } from '../components/InstrumentDetail';
import tableStyles from '../styles/table.module.css';
import { MAX_TRADING_SIGNAL_ROWS } from '../constants/renderLimits';

export default function Trading() {
  const { t } = useTranslation();
  const [signals, setSignals] = useState<TradingSignal[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<TradingSignal | null>(null);

  useEffect(() => {
    getTradingSignals()
      .then(setSignals)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  if (error) {
    return <p style={{ color: 'red' }}>{error}</p>;
  }

  if (!signals.length) {
    return <p>{t('trading.noSignals')}</p>;
  }
  const visibleSignals = signals.slice(0, MAX_TRADING_SIGNAL_ROWS);

  const formatAction = (action: string) => {
    if (!action) {
      return action;
    }
    const lower = action.toLowerCase();
    return lower.charAt(0).toUpperCase() + lower.slice(1);
  };

  const renderStrength = (confidence?: number | null) => {
    if (confidence == null) {
      return '—';
    }

    const percent = Math.round(confidence * 100);
    let label = 'Weak';
    if (confidence >= 0.75) {
      label = 'Strong';
    } else if (confidence >= 0.5) {
      label = 'Moderate';
    }

    return `${label} (${percent}%)`;
  };

  const renderFactors = (factors?: string[], fallback?: string) => {
    if (factors && factors.length) {
      return (
        <ul style={{ margin: 0, paddingLeft: '1.1rem' }}>
          {factors.map((factor, idx) => (
            <li key={idx}>{factor}</li>
          ))}
        </ul>
      );
    }
    if (fallback) {
      return <span>{fallback}</span>;
    }
    return '—';
  };

  return (
    <>
      <table className={tableStyles.table}>
        <caption>{t('trading.signalsTableCaption', 'Trading signals')}</caption>
        <thead>
          <tr>
            <th className={tableStyles.cell}>Ticker</th>
            <th className={tableStyles.cell}>Action</th>
            <th className={tableStyles.cell}>Strength</th>
            <th className={tableStyles.cell}>Summary</th>
            <th className={tableStyles.cell}>Why</th>
          </tr>
        </thead>
        <tbody>
          {visibleSignals.map((s) => (
            <tr key={s.ticker}>
              <td className={tableStyles.cell}>
                <button
                  type="button"
                  className={tableStyles.clickable}
                  onClick={() => setSelected(s)}
                >
                  {s.ticker}
                </button>
              </td>
              <td className={tableStyles.cell}>{formatAction(s.action)}</td>
              <td className={tableStyles.cell}>{renderStrength(s.confidence)}</td>
              <td className={tableStyles.cell}>{s.reason}</td>
              <td className={tableStyles.cell}>{renderFactors(s.factors, s.rationale)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {signals.length > MAX_TRADING_SIGNAL_ROWS && (
        <p>
          Showing first {MAX_TRADING_SIGNAL_ROWS.toLocaleString()} signals of{' '}
          {signals.length.toLocaleString()}.
        </p>
      )}
      {selected && (
        <InstrumentDetail
          ticker={selected.ticker}
          name={selected.name ?? selected.ticker}
          currency={selected.currency ?? undefined}
          instrument_type={selected.instrument_type}
          signal={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}
