import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { createDecisionDraft, getDecisionJournal } from '../api';
import { qualifyingTrades } from '../lib/decisionJournalPrompt';
import type { DecisionDraft, Transaction, UnloggedChange } from '../types';
import { DraftEditor } from './DecisionJournal';

const BUTTON = 'rounded bg-gray-200 px-2 py-1 text-sm text-slate-900';
const PRIMARY = 'rounded bg-blue-500 px-2 py-1 text-sm text-white';
const gbp = new Intl.NumberFormat('en-GB', {
  style: 'currency',
  currency: 'GBP',
  maximumFractionDigits: 0,
});

const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);

/** Loads the owner's journal threshold and picks the trades that reach it. */
function useQualifying(owner: string, trades: Transaction[]) {
  const [changes, setChanges] = useState<UnloggedChange[]>([]);
  const [threshold, setThreshold] = useState(0);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    getDecisionJournal(owner)
      .then((journal) => {
        if (!active) return;
        setThreshold(journal.settings.threshold_gbp);
        setChanges(qualifyingTrades(trades, journal.settings.threshold_gbp));
      })
      .catch((err: unknown) => {
        if (active) setError(errorText(err));
      });
    return () => {
      active = false;
    };
  }, [owner, trades]);
  return { changes, setChanges, threshold, error, setError };
}

/**
 * "Log this decision?" straight after trades are recorded or imported
 * (#10488). Lists every trade at or above the owner's journal threshold in
 * one prompt; each opens the same pre-filled draft as the plan panel.
 *
 * Non-blocking: the trades are already saved. Dismissing writes nothing,
 * so the trades stay listed as unlogged in the plan panel; only confirming
 * a draft with the owner's reasoning writes to the plan.
 */
export function TradeJournalPrompt({
  owner,
  trades,
  onClose,
}: {
  owner: string;
  /** Transactions just saved, as returned by the API (with their ids). */
  trades: Transaction[];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { changes, setChanges, threshold, error, setError } = useQualifying(
    owner,
    trades
  );
  const [draft, setDraft] = useState<DecisionDraft | null>(null);

  const openDraft = async (change: UnloggedChange) => {
    try {
      setDraft(
        await createDecisionDraft(owner, { source_ref: change.source_ref })
      );
      setError(null);
    } catch (err) {
      setError(errorText(err));
    }
  };

  const draftDone = (logged: boolean) => {
    const ref = draft?.source_ref;
    setDraft(null);
    if (!logged) return;
    const remaining = changes.filter((c) => c.source_ref !== ref);
    setChanges(remaining);
    if (remaining.length === 0) onClose();
  };

  if (!error && changes.length === 0) return null;
  return (
    <div
      className="mb-3 rounded border p-2 text-sm"
      role="region"
      aria-label={t('decisionJournal.tradePromptLabel')}
    >
      {draft ? (
        <DraftEditor
          key={draft.id}
          owner={owner}
          initial={draft}
          onDone={draftDone}
        />
      ) : (
        <>
          {changes.length > 0 && (
            <>
              <p className="mb-1">
                {t('decisionJournal.tradePrompt', {
                  threshold: gbp.format(threshold),
                })}
              </p>
              <ul className="mb-2">
                {changes.map((c) => (
                  <li
                    key={c.source_ref}
                    className="mb-1 flex flex-wrap items-center gap-2"
                  >
                    <span>
                      {t('decisionJournal.logPrompt', {
                        type: c.type,
                        amount: gbp.format(c.amount_gbp),
                        ticker: c.ticker,
                        date: c.date,
                      })}
                    </span>
                    <button
                      type="button"
                      className={PRIMARY}
                      onClick={() => void openDraft(c)}
                    >
                      {t('decisionJournal.logThis')}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
          {error && (
            <p className="mb-1 break-words text-red-600">
              {t('decisionJournal.tradePromptError', { message: error })}
            </p>
          )}
          <button type="button" className={BUTTON} onClick={onClose}>
            {t('decisionJournal.dismiss')}
          </button>
        </>
      )}
    </div>
  );
}
