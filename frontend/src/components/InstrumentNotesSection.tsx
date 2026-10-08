import { useCallback, useEffect, useRef, useState } from 'react';
import type { CSSProperties, FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import {
  createInstrumentNote,
  deleteInstrumentNote,
  getInstrumentNotes,
} from '../api';
import type { InstrumentNote, InstrumentNoteStance } from '../api';
import { useAlertIdentity } from '../hooks/useAlertIdentity';
import { useDemoReadOnly } from '../hooks/useDemoReadOnly';

const MAX_NOTE_LENGTH = 2000;
const STANCES: InstrumentNoteStance[] = ['bullish', 'neutral', 'bearish'];

const STANCE_COLOURS: Record<InstrumentNoteStance, string> = {
  bullish: '#137333',
  bearish: '#b3261e',
  neutral: '#555',
};

interface Props {
  /** Ticker the notes belong to (e.g. "REC.L"). */
  ticker: string;
  /** Latest GBP close, saved with each new note and used for "since" moves. */
  latestPrice?: number | null;
  /** Reports how many notes this instrument has after each (re)load. */
  onCountChange?: (count: number) => void;
}

function errorMessage(err: unknown, fallback: string): string {
  return (err as { message?: string })?.message || fallback;
}

function usablePrice(price: number | null | undefined): number | null {
  return typeof price === 'number' && Number.isFinite(price) && price > 0
    ? price
    : null;
}

function formatChange(from: number, to: number): string {
  const pct = ((to - from) / from) * 100;
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`;
}

function StanceBadge({ stance }: { stance: InstrumentNoteStance }) {
  const { t } = useTranslation();
  const style: CSSProperties = {
    color: '#fff',
    background: STANCE_COLOURS[stance],
    borderRadius: '999px',
    padding: '0.1rem 0.5rem',
    fontSize: '0.8em',
    fontWeight: 600,
  };
  return <span style={style}>{t(`instrumentNotes.${stance}`)}</span>;
}

interface NoteItemProps {
  note: InstrumentNote;
  latestPrice: number | null;
  disabled: boolean;
  onDelete: (note: InstrumentNote) => void;
}

function NoteItem({ note, latestPrice, disabled, onDelete }: NoteItemProps) {
  const { t } = useTranslation();
  const then = usablePrice(note.price);
  return (
    <li style={{ marginBottom: '1rem', listStyle: 'none' }}>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '0.5rem',
          alignItems: 'center',
        }}
      >
        <StanceBadge stance={note.stance} />
        <time dateTime={note.created_at} style={{ fontSize: '0.85em' }}>
          {new Date(note.created_at).toLocaleString()}
        </time>
        {then !== null && (
          <span style={{ fontSize: '0.85em' }}>
            {t('instrumentNotes.priceAt', { price: then.toFixed(2) })}
            {latestPrice !== null &&
              ` · ${t('instrumentNotes.sinceThen', { change: formatChange(then, latestPrice) })}`}
          </span>
        )}
        <button
          type="button"
          onClick={() => onDelete(note)}
          disabled={disabled}
        >
          {t('instrumentNotes.delete')}
        </button>
      </div>
      <p style={{ whiteSpace: 'pre-wrap', margin: '0.25rem 0 0' }}>
        {note.text}
      </p>
    </li>
  );
}

interface NoteFormProps {
  disabled: boolean;
  disabledReason?: string;
  onSubmit: (stance: InstrumentNoteStance, text: string) => Promise<boolean>;
}

function NoteForm({ disabled, disabledReason, onSubmit }: NoteFormProps) {
  const { t } = useTranslation();
  const [stance, setStance] = useState<InstrumentNoteStance>('neutral');
  const [text, setText] = useState('');

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (disabled || !text.trim()) return;
    if (await onSubmit(stance, text.trim())) setText('');
  }

  return (
    <form
      onSubmit={submit}
      style={{ display: 'grid', gap: '0.5rem', marginBottom: '1rem' }}
    >
      <textarea
        aria-label={t('instrumentNotes.text')}
        placeholder={t('instrumentNotes.placeholder')}
        value={text}
        maxLength={MAX_NOTE_LENGTH}
        rows={3}
        onChange={(e) => setText(e.target.value)}
        disabled={disabled}
      />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
        <select
          aria-label={t('instrumentNotes.stance')}
          value={stance}
          onChange={(e) => setStance(e.target.value as InstrumentNoteStance)}
          disabled={disabled}
        >
          {STANCES.map((s) => (
            <option key={s} value={s}>
              {t(`instrumentNotes.${s}`)}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={disabled || !text.trim()}
          title={disabledReason}
        >
          {t('instrumentNotes.add')}
        </button>
      </div>
    </form>
  );
}

interface PanelProps extends Props {
  identity: string;
  disabled: boolean;
  disabledReason?: string;
}

function useNotes(
  identity: string,
  ticker: string,
  onCountChange?: (count: number) => void
) {
  const { t } = useTranslation();
  const [notes, setNotes] = useState<InstrumentNote[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Held in a ref so an inline callback from the parent doesn't change
  // `reload`'s identity and re-fetch on every render.
  const onCountRef = useRef(onCountChange);
  onCountRef.current = onCountChange;

  const reload = useCallback(async () => {
    try {
      const rows = await getInstrumentNotes(identity, ticker);
      setNotes(rows);
      onCountRef.current?.(rows.length);
      setError(null);
    } catch (err) {
      setError(errorMessage(err, t('instrumentNotes.loadError')));
    }
  }, [identity, ticker, t]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { notes, error, setError, reload };
}

function InstrumentNotesPanel({
  identity,
  disabled,
  disabledReason,
  ticker,
  latestPrice,
  onCountChange,
}: PanelProps) {
  const { t } = useTranslation();
  const { notes, error, setError, reload } = useNotes(
    identity,
    ticker,
    onCountChange
  );
  const [busy, setBusy] = useState(false);
  const price = usablePrice(latestPrice);

  async function run(
    action: () => Promise<unknown>,
    failure: string
  ): Promise<boolean> {
    setBusy(true);
    try {
      await action();
      await reload();
      return true;
    } catch (err) {
      setError(errorMessage(err, failure));
      return false;
    } finally {
      setBusy(false);
    }
  }

  const add = (stance: InstrumentNoteStance, text: string) =>
    run(
      () => createInstrumentNote(identity, { ticker, stance, text, price }),
      t('instrumentNotes.saveError')
    );

  function remove(note: InstrumentNote) {
    if (!window.confirm(t('instrumentNotes.deleteConfirm'))) return;
    void run(
      () => deleteInstrumentNote(identity, note.id),
      t('instrumentNotes.deleteError')
    );
  }

  return (
    <section
      aria-labelledby="instrument-notes-title"
      style={{ marginBottom: '1rem' }}
    >
      <h2 id="instrument-notes-title">{t('instrumentNotes.title')}</h2>
      <p>{t('instrumentNotes.description', { ticker })}</p>
      <NoteForm
        disabled={disabled || busy}
        disabledReason={disabledReason}
        onSubmit={add}
      />
      {error && <p role="alert">{error}</p>}
      {notes.length === 0 ? (
        <p>{t('instrumentNotes.empty', { ticker })}</p>
      ) : (
        <ul style={{ padding: 0 }}>
          {notes.map((note) => (
            <NoteItem
              key={note.id}
              note={note}
              latestPrice={price}
              disabled={disabled || busy}
              onDelete={remove}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * Timestamped, stance-tagged research notes for one instrument on the
 * research page. Stored per resolved identity (see useAlertIdentity), like
 * price alerts.
 */
export default function InstrumentNotesSection(props: Props) {
  const { t } = useTranslation();
  const { identity, resolving } = useAlertIdentity();
  const { demoReadOnly, reason } = useDemoReadOnly();

  if (!props.ticker || resolving) return null;
  if (!identity) return <p>{t('instrumentNotes.signInNotice')}</p>;
  return (
    <InstrumentNotesPanel
      {...props}
      identity={identity}
      disabled={demoReadOnly}
      disabledReason={reason()}
    />
  );
}
