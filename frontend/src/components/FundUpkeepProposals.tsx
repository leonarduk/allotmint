import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { decideFundUpkeepProposal, getFundUpkeepProposals } from '../api';
import { percent } from '../lib/money';
import type { FundUpkeepProposal } from '../types';

type Action = 'approve' | 'reject' | 'undo';

function describeValue(p: FundUpkeepProposal, label: string): string {
  if (p.kind === 'ongoing_charge' && typeof p.value === 'number') {
    return `${label}: ${percent(p.value)}`;
  }
  return label;
}

/**
 * Review queue for the fund data upkeep bot (#10482). Each proposal shows the
 * public document it came from and that document's date; nothing is written
 * to instrument metadata until it is approved, and an approval can be undone.
 */
export function FundUpkeepProposals() {
  const { t } = useTranslation();
  const [items, setItems] = useState<FundUpkeepProposal[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const all = await getFundUpkeepProposals();
      setItems(
        all.filter((p) => p.status === 'pending' || p.status === 'approved')
      );
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(t('fundUpkeep.loadFailed', { message }));
    }
  }, [t]);

  useEffect(() => {
    void load(); // errors are reported through `error` state inside load()
  }, [load]);

  const act = async (id: string, action: Action) => {
    setBusyId(id);
    try {
      await decideFundUpkeepProposal(id, action);
      await load();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(t('fundUpkeep.actionFailed', { message }));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section data-testid="fund-upkeep-proposals" style={{ marginTop: '2rem' }}>
      <h3 className="mb-2 text-lg">{t('fundUpkeep.title')}</h3>
      <p style={{ fontSize: '0.9rem' }}>{t('fundUpkeep.description')}</p>
      {error && <p role="alert">{error}</p>}
      {items !== null && items.length === 0 && <p>{t('fundUpkeep.empty')}</p>}
      {items !== null && items.length > 0 && (
        <ul>
          {items.map((p) => {
            const label =
              p.kind === 'ongoing_charge'
                ? t('fundUpkeep.ongoingCharge')
                : t('fundUpkeep.lookThrough');
            const busy = busyId === p.id;
            return (
              <li key={p.id} data-testid={`fund-upkeep-proposal-${p.id}`}>
                <strong>{p.ticker}</strong> {describeValue(p, label)} -{' '}
                <a href={p.source_url} target="_blank" rel="noopener noreferrer">
                  {t('fundUpkeep.source')}
                </a>{' '}
                ({t('fundUpkeep.documentDate', { date: p.document_date })}) -{' '}
                {t(`fundUpkeep.status.${p.status}`)}{' '}
                {p.status === 'pending' && (
                  <>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void act(p.id, 'approve')}
                    >
                      {t('fundUpkeep.approve')}
                    </button>{' '}
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void act(p.id, 'reject')}
                    >
                      {t('fundUpkeep.reject')}
                    </button>
                  </>
                )}
                {p.status === 'approved' && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void act(p.id, 'undo')}
                  >
                    {t('fundUpkeep.undo')}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export default FundUpkeepProposals;
