import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  confirmDecision,
  createDecisionDraft,
  dismissDecisionChange,
  getDecisionJournal,
  getInvestmentPlan,
  runDecisionJournal,
  saveDecisionLesson,
} from '../api';
import type {
  DecisionDraft,
  DecisionJournalEntry,
  DecisionJournalResponse,
  DecisionLeg,
  DecisionReview,
  InvestmentPlanDecision,
  UnloggedChange,
} from '../types';

const INPUT = 'w-full border p-1 text-sm';
const BUTTON = 'rounded bg-gray-200 px-2 py-1 text-sm text-slate-900';
const PRIMARY =
  'rounded bg-blue-500 px-2 py-1 text-sm text-white disabled:opacity-50';
const gbp = new Intl.NumberFormat('en-GB', {
  style: 'currency',
  currency: 'GBP',
  maximumFractionDigits: 0,
});

const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);

/** The plan target before and after an edit, offered for logging. */
export interface PlanTargetChange {
  previous: Record<string, number>;
  current: Record<string, number>;
}

/** A draft as the owner edits it: alternatives one per line, legs with text tickers. */
interface DraftForm {
  draft: DecisionDraft;
  decision: string;
  alternatives: string;
  reason: string;
  expectation: string;
  legs: { role: DecisionLeg['role']; label: string; ticker: string }[];
  checkLeg: string;
  checkOutperforms: string;
}

function toForm(draft: DecisionDraft): DraftForm {
  return {
    draft,
    decision: draft.decision,
    alternatives: draft.alternatives.join('\n'),
    reason: '',
    expectation: '',
    legs: draft.legs.map((l) => ({ ...l, ticker: l.ticker ?? '' })),
    checkLeg: '',
    checkOutperforms: '',
  };
}

/** Form -> confirm payload; a blank ticker is cash. */
function fromForm(form: DraftForm) {
  const legs = form.legs
    .filter((l) => l.label.trim())
    .map((l) => ({
      role: l.role,
      label: l.label.trim(),
      ticker: l.ticker.trim().toUpperCase() || null,
    }));
  const check =
    form.checkLeg && form.checkOutperforms
      ? { leg: form.checkLeg, outperforms: form.checkOutperforms }
      : undefined;
  return {
    ...form.draft,
    decision: form.decision.trim(),
    alternatives: form.alternatives
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean),
    reason: form.reason.trim(),
    legs,
    expectation: form.expectation.trim()
      ? { text: form.expectation.trim(), check }
      : undefined,
  };
}

/** The plan's decisions (for each entry's text); none when no plan is saved yet. */
async function planDecisions(owner: string): Promise<InvestmentPlanDecision[]> {
  try {
    return (await getInvestmentPlan(owner)).plan.decisions;
  } catch (err) {
    if ((err as { status?: number } | null)?.status === 404) return [];
    throw err;
  }
}

function useJournal(owner: string) {
  const [data, setData] = useState<DecisionJournalResponse | null>(null);
  const [decisions, setDecisions] = useState<InvestmentPlanDecision[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      const [journal, logged] = await Promise.all([
        getDecisionJournal(owner),
        planDecisions(owner),
      ]);
      setData(journal);
      setDecisions(logged);
      setError(null);
    } catch (err) {
      setError(errorText(err));
    }
  }, [owner]);
  useEffect(() => {
    setData(null);
    setDecisions([]);
    void load(); // errors are captured into state inside load
  }, [load]);
  return { data, decisions, error, setError, load };
}

function UnloggedList({
  changes,
  onLog,
  onDismiss,
}: {
  changes: UnloggedChange[];
  onLog: (change: UnloggedChange) => void;
  onDismiss: (change: UnloggedChange) => void;
}) {
  const { t } = useTranslation();
  if (!changes.length) return null;
  return (
    <ul className="mb-2 text-sm" aria-label={t('decisionJournal.unlogged')}>
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
          <button type="button" className={PRIMARY} onClick={() => onLog(c)}>
            {t('decisionJournal.logThis')}
          </button>
          <button type="button" className={BUTTON} onClick={() => onDismiss(c)}>
            {t('decisionJournal.notNow')}
          </button>
        </li>
      ))}
    </ul>
  );
}

function SnapshotFacts({ snapshot }: { snapshot: Record<string, unknown> }) {
  const { t } = useTranslation();
  const weights = snapshot.weights as
    { before_pct?: number | null; after_pct?: number | null } | undefined;
  return (
    <details className="mb-2 text-xs">
      <summary className="cursor-pointer">
        {t('decisionJournal.snapshot')}
        {weights?.before_pct != null && weights.after_pct != null
          ? ` · ${t('decisionJournal.weights', { before: weights.before_pct, after: weights.after_pct })}`
          : ''}
      </summary>
      <pre className="overflow-x-auto whitespace-pre-wrap">
        {JSON.stringify(snapshot, null, 2)}
      </pre>
    </details>
  );
}

function LegsEditor({
  form,
  patch,
}: {
  form: DraftForm;
  patch: (p: Partial<DraftForm>) => void;
}) {
  const { t } = useTranslation();
  const setLeg = (i: number, p: Partial<DraftForm['legs'][number]>) =>
    patch({ legs: form.legs.map((l, j) => (j === i ? { ...l, ...p } : l)) });
  const addAlternative = () =>
    patch({
      legs: [...form.legs, { role: 'alternative', label: '', ticker: '' }],
    });
  return (
    <fieldset className="mb-2">
      <legend className="text-sm font-medium">
        {t('decisionJournal.legs')}
      </legend>
      <p className="text-xs text-slate-500 dark:text-slate-400">
        {t('decisionJournal.legsHelp')}
      </p>
      {form.legs.map((leg, i) => (
        <div key={i} className="mb-1 flex gap-2">
          <span className="w-24 text-xs">
            {t(`decisionJournal.role_${leg.role}`)}
          </span>
          <input
            className={INPUT}
            aria-label={t('decisionJournal.legLabel', { n: i + 1 })}
            value={leg.label}
            onChange={(e) => setLeg(i, { label: e.target.value })}
          />
          <input
            className={INPUT}
            aria-label={t('decisionJournal.legTicker', { n: i + 1 })}
            placeholder={t('decisionJournal.cash')}
            value={leg.ticker}
            onChange={(e) => setLeg(i, { ticker: e.target.value })}
          />
        </div>
      ))}
      <button type="button" className={BUTTON} onClick={addAlternative}>
        {t('decisionJournal.addAlternative')}
      </button>
    </fieldset>
  );
}

function ExpectationFields({
  form,
  patch,
}: {
  form: DraftForm;
  patch: (p: Partial<DraftForm>) => void;
}) {
  const { t } = useTranslation();
  const labels = form.legs.map((l) => l.label.trim()).filter(Boolean);
  const select = (key: 'checkLeg' | 'checkOutperforms', label: string) => (
    <select
      className="border p-1 text-sm"
      aria-label={label}
      value={form[key]}
      onChange={(e) => patch({ [key]: e.target.value })}
    >
      <option value="">—</option>
      {labels.map((l) => (
        <option key={l} value={l}>
          {l}
        </option>
      ))}
    </select>
  );
  return (
    <div className="mb-2">
      <input
        className={INPUT}
        aria-label={t('decisionJournal.expectation')}
        placeholder={t('decisionJournal.expectationPlaceholder')}
        value={form.expectation}
        onChange={(e) => patch({ expectation: e.target.value })}
      />
      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
        {t('decisionJournal.checkPrefix')}
        {select('checkLeg', t('decisionJournal.checkLeg'))}
        {t('decisionJournal.checkOutperforms')}
        {select('checkOutperforms', t('decisionJournal.checkOther'))}
      </div>
    </div>
  );
}

function DraftEditor({
  owner,
  initial,
  onDone,
}: {
  owner: string;
  initial: DecisionDraft;
  onDone: (logged: boolean) => void;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState(() => toForm(initial));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const patch = (p: Partial<DraftForm>) => setForm((f) => ({ ...f, ...p }));
  async function confirm() {
    setSaving(true);
    setError(null);
    try {
      await confirmDecision(owner, fromForm(form));
      onDone(true);
    } catch (err) {
      setError(errorText(err));
      setSaving(false);
    }
  }
  return (
    <div
      className="mb-3 rounded border p-2"
      role="group"
      aria-label={t('decisionJournal.draft')}
    >
      <SnapshotFacts snapshot={initial.snapshot} />
      <input
        className={`${INPUT} mb-2`}
        aria-label={t('decisionJournal.decision')}
        value={form.decision}
        onChange={(e) => patch({ decision: e.target.value })}
      />
      <textarea
        className={`${INPUT} mb-2`}
        rows={2}
        aria-label={t('decisionJournal.alternatives')}
        placeholder={t('decisionJournal.alternativesPlaceholder')}
        value={form.alternatives}
        onChange={(e) => patch({ alternatives: e.target.value })}
      />
      <textarea
        className={`${INPUT} mb-2`}
        rows={3}
        aria-label={t('decisionJournal.reason')}
        placeholder={t('decisionJournal.reasonPlaceholder')}
        value={form.reason}
        onChange={(e) => patch({ reason: e.target.value })}
      />
      <ExpectationFields form={form} patch={patch} />
      <LegsEditor form={form} patch={patch} />
      <div className="flex gap-2">
        <button
          type="button"
          className={PRIMARY}
          disabled={saving || !form.reason.trim() || !form.decision.trim()}
          onClick={() => void confirm()}
        >
          {t('decisionJournal.confirm')}
        </button>
        <button type="button" className={BUTTON} onClick={() => onDone(false)}>
          {t('decisionJournal.cancel')}
        </button>
      </div>
      {error && (
        <p className="mt-1 break-words text-sm text-red-600">{error}</p>
      )}
    </div>
  );
}

function LessonInput({
  owner,
  entryId,
  review,
}: {
  owner: string;
  entryId: string;
  review: DecisionReview;
}) {
  const { t } = useTranslation();
  const [lesson, setLesson] = useState(review.lesson ?? '');
  const [status, setStatus] = useState<string | null>(null);
  async function save() {
    try {
      await saveDecisionLesson(owner, entryId, review.horizon_months, lesson);
      setStatus(t('decisionJournal.lessonSaved'));
    } catch (err) {
      setStatus(errorText(err));
    }
  }
  return (
    <div className="mt-1 flex gap-2">
      <input
        className={INPUT}
        aria-label={t('decisionJournal.lesson', {
          months: review.horizon_months,
        })}
        placeholder={t('decisionJournal.lessonPlaceholder')}
        value={lesson}
        onChange={(e) => setLesson(e.target.value)}
      />
      <button type="button" className={BUTTON} onClick={() => void save()}>
        {t('decisionJournal.saveLesson')}
      </button>
      {status && <span className="text-xs">{status}</span>}
    </div>
  );
}

function EntryItem({
  owner,
  entry,
  decision,
}: {
  owner: string;
  entry: DecisionJournalEntry;
  decision?: InvestmentPlanDecision;
}) {
  const { t } = useTranslation();
  const pending = entry.review_due.filter(
    (_due, i) => i >= entry.reviews.length
  );
  return (
    <li className="mb-2">
      <p className="font-medium">
        {entry.date}: {decision?.decision ?? entry.id}
      </p>
      {entry.expectation && (
        <p className="text-xs">
          {t('decisionJournal.expected', { text: entry.expectation.text })}
        </p>
      )}
      {entry.reviews.map((review) => (
        <div key={review.horizon_months} className="mt-1 border-l pl-2">
          <ul className="text-xs">
            {review.summary.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <LessonInput owner={owner} entryId={entry.id} review={review} />
        </div>
      ))}
      {pending.length > 0 && (
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {t('decisionJournal.reviewsDue', { dates: pending.join(', ') })}
        </p>
      )}
    </li>
  );
}

function useJournalActions(
  owner: string,
  {
    load,
    setError,
    setDraft,
  }: {
    load: () => Promise<void>;
    setError: (error: string | null) => void;
    setDraft: (draft: DecisionDraft | null) => void;
  },
  onPlanChangeHandled?: () => void
) {
  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
    } catch (err) {
      setError(errorText(err));
    }
  };
  return {
    logTrade: (c: UnloggedChange) =>
      act(async () =>
        setDraft(await createDecisionDraft(owner, { source_ref: c.source_ref }))
      ),
    logPlanChange: (change: PlanTargetChange) =>
      act(async () => {
        setDraft(
          await createDecisionDraft(owner, {
            previous_target: change.previous,
            target: change.current,
          })
        );
        onPlanChangeHandled?.();
      }),
    dismiss: (c: UnloggedChange) =>
      act(async () => {
        await dismissDecisionChange(owner, c.source_ref);
        await load();
      }),
    runNow: () =>
      act(async () => {
        await runDecisionJournal(owner);
        await load();
      }),
  };
}

function PlanChangePrompt({
  onLog,
  onDismiss,
}: {
  onLog: () => void;
  onDismiss: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div
      className="mb-2 flex flex-wrap items-center gap-2 text-sm"
      role="status"
    >
      <span>{t('decisionJournal.planChangePrompt')}</span>
      <button type="button" className={PRIMARY} onClick={onLog}>
        {t('decisionJournal.logThis')}
      </button>
      <button type="button" className={BUTTON} onClick={onDismiss}>
        {t('decisionJournal.notNow')}
      </button>
    </div>
  );
}

/**
 * Decision journal (#10481): prompts to log qualifying trades and plan target
 * changes, pre-filled with facts the owner completes with their own
 * reasoning, and the 6/12-month reviews against the alternatives they listed.
 */
export default function DecisionJournal({
  owner,
  planChange = null,
  onPlanChangeHandled,
  onLogged,
}: {
  owner: string;
  planChange?: PlanTargetChange | null;
  onPlanChangeHandled?: () => void;
  /** Called after a decision is written to the plan. */
  onLogged?: () => void;
}) {
  const { t } = useTranslation();
  const { data, decisions, error, setError, load } = useJournal(owner);
  const [draft, setDraft] = useState<DecisionDraft | null>(null);
  const { logTrade, logPlanChange, dismiss, runNow } = useJournalActions(
    owner,
    { load, setError, setDraft },
    onPlanChangeHandled
  );
  const byId = new Map(decisions.filter((d) => d.id).map((d) => [d.id, d]));

  return (
    <section
      className="mb-6 rounded border p-4"
      aria-label={t('decisionJournal.title')}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl">{t('decisionJournal.title')}</h2>
        <button type="button" className={BUTTON} onClick={() => void runNow()}>
          {t('decisionJournal.runNow')}
        </button>
      </div>
      <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
        {t('decisionJournal.subtitle', {
          threshold: gbp.format(data?.settings.threshold_gbp ?? 0),
        })}
      </p>
      {planChange && !draft && (
        <PlanChangePrompt
          onLog={() => void logPlanChange(planChange)}
          onDismiss={() => onPlanChangeHandled?.()}
        />
      )}
      {draft ? (
        <DraftEditor
          key={draft.id}
          owner={owner}
          initial={draft}
          onDone={(logged) => {
            setDraft(null);
            if (logged) {
              onLogged?.();
              void load();
            }
          }}
        />
      ) : (
        <UnloggedList
          changes={data?.unlogged ?? []}
          onLog={(c) => void logTrade(c)}
          onDismiss={(c) => void dismiss(c)}
        />
      )}
      {error && <p className="break-words text-sm text-red-600">{error}</p>}
      {data && data.entries.length > 0 && (
        <ul className="text-sm" aria-label={t('decisionJournal.entries')}>
          {data.entries.map((entry) => (
            <EntryItem
              key={entry.id}
              owner={owner}
              entry={entry}
              decision={byId.get(entry.id)}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
