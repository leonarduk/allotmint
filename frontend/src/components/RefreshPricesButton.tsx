import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { refetchTimeseries } from '../api';

type RefreshPricesButtonProps = {
  ticker: string;
  exchange: string;
  onRefreshed?: (rows: number) => void;
};

/**
 * "Refresh prices" action for the Research page (#9963): re-fetches the price
 * series from upstream, bypassing the backend's in-process caches, so a newly
 * added instrument gets history without a backend restart.
 */
export function RefreshPricesButton({
  ticker,
  exchange,
  onRefreshed,
}: RefreshPricesButtonProps) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{
    kind: 'success' | 'error';
    text: string;
  } | null>(null);

  async function handleRefresh() {
    setBusy(true);
    setMessage(null);
    try {
      const { rows } = await refetchTimeseries(ticker, exchange);
      setMessage({
        kind: 'success',
        text: t('instrumentDetail.research.refreshPricesDone', { rows }),
      });
      onRefreshed?.(rows);
    } catch (e) {
      const detail = e instanceof Error ? e.message : String(e);
      setMessage({
        kind: 'error',
        text: `${t('instrumentDetail.research.refreshPricesError')} ${detail}`,
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={handleRefresh}
        disabled={busy}
        style={{ marginLeft: '1rem' }}
      >
        {busy
          ? t('instrumentDetail.research.refreshingPrices')
          : t('instrumentDetail.research.refreshPrices')}
      </button>
      {message && (
        <span
          role={message.kind === 'error' ? 'alert' : 'status'}
          style={{ marginLeft: '1rem' }}
        >
          {message.text}
        </span>
      )}
    </>
  );
}

export default RefreshPricesButton;
