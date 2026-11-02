import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { attributeDividend } from '../api';
import type { Transaction } from '../types';
import { unattributedDividends } from '../lib/dividends';

interface Part {
  ticker: string;
  pounds: string;
}

const toMinor = (pounds: string): number => Math.round(Number(pounds) * 100);

const formatPounds = (minor: number) => `£${(minor / 100).toFixed(2)}`;

function partsError(parts: Part[], totalMinor: number): string | null {
  const filled = parts.filter((p) => p.ticker.trim() || p.pounds.trim());
  if (!filled.length) return 'dividends.attribute.needPart';
  if (filled.some((p) => !p.ticker.trim()))
    return 'dividends.attribute.needTicker';
  if (filled.some((p) => !(toMinor(p.pounds) > 0)))
    return 'dividends.attribute.needAmount';
  const used = filled.reduce((sum, p) => sum + toMinor(p.pounds), 0);
  return used > totalMinor ? 'dividends.attribute.tooMuch' : null;
}

function PartInputs({
  parts,
  listId,
  setPart,
}: {
  parts: Part[];
  listId: string;
  setPart: (index: number, patch: Partial<Part>) => void;
}) {
  const { t } = useTranslation();
  return (
    <>
      {parts.map((part, index) => (
        <div key={index} style={{ display: 'flex', gap: '0.5rem' }}>
          <input
            aria-label={t('dividends.attribute.ticker')}
            list={listId}
            value={part.ticker}
            onChange={(e) => setPart(index, { ticker: e.target.value })}
          />
          <input
            aria-label={t('dividends.attribute.amount')}
            type="number"
            min="0"
            step="0.01"
            value={part.pounds}
            onChange={(e) => setPart(index, { pounds: e.target.value })}
          />
        </div>
      ))}
    </>
  );
}

function AttributionForm({
  tx,
  tickers,
  onDone,
}: {
  tx: Transaction;
  tickers: string[];
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const totalMinor = tx.amount_minor ?? 0;
  const [parts, setParts] = useState<Part[]>([{ ticker: '', pounds: '' }]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const used = parts.reduce((sum, p) => sum + (toMinor(p.pounds) || 0), 0);
  const listId = `dividend-attribution-tickers-${tx.id}`;

  const setPart = (index: number, patch: Partial<Part>) =>
    setParts(parts.map((p, i) => (i === index ? { ...p, ...patch } : p)));

  const save = async () => {
    const problem = partsError(parts, totalMinor);
    if (problem) {
      setError(t(problem));
      return;
    }
    setSaving(true);
    try {
      await attributeDividend(
        tx.id as string,
        parts
          .filter((p) => p.ticker.trim())
          .map((p) => ({
            ticker: p.ticker.trim().toUpperCase(),
            amount_minor: toMinor(p.pounds),
          }))
      );
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ margin: '0.5rem 0 1rem' }}>
      <datalist id={listId}>
        {tickers.map((ticker) => (
          <option key={ticker} value={ticker} />
        ))}
      </datalist>
      <PartInputs parts={parts} listId={listId} setPart={setPart} />
      <p>
        {t('dividends.attribute.remaining', {
          amount: formatPounds(Math.max(totalMinor - used, 0)),
        })}
      </p>
      {error && <p role="alert">{error}</p>}
      <button
        type="button"
        onClick={() => setParts([...parts, { ticker: '', pounds: '' }])}
      >
        {t('dividends.attribute.addHolding')}
      </button>{' '}
      <button type="button" disabled={saving} onClick={() => void save()}>
        {t('dividends.attribute.save')}
      </button>
    </div>
  );
}

export default function DividendAttribution({
  transactions,
  tickers,
  onAttributed,
}: {
  transactions: Transaction[];
  tickers: string[];
  onAttributed: () => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState<string | null>(null);
  const rows = unattributedDividends(transactions);
  if (!rows.length) return null;

  return (
    <details data-testid="dividend-attribution">
      <summary>
        {t('dividends.attribute.title', { count: rows.length })}
      </summary>
      <p>{t('dividends.attribute.help')}</p>
      <ul>
        {rows.map((tx) => (
          <li key={tx.id as string}>
            {tx.date?.slice(0, 10)} · {tx.owner} {tx.account} ·{' '}
            {formatPounds(tx.amount_minor ?? 0)}{' '}
            {open === tx.id ? (
              <AttributionForm
                tx={tx}
                tickers={tickers}
                onDone={() => {
                  setOpen(null);
                  onAttributed();
                }}
              />
            ) : (
              <button type="button" onClick={() => setOpen(tx.id as string)}>
                {t('dividends.attribute.split')}
              </button>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}
