import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { saveInvestmentPlan } from '../api';
import { localDateISO } from '../lib/date';
import {
  GOAL_PURPOSES,
  PLAN_CLASSES,
  PLAN_STATUSES,
  PROFILE_LEVELS,
  classLabel,
  formErrors,
  isPlanClass,
  fromPlan,
  targetTotal,
  toPlan,
  type AssumptionRow,
  type DecisionRow,
  type EvidenceRow,
  type GoalRow,
  type PlanForm,
  type RatingFields,
  type TargetRow,
  type TextRow,
  type VehicleRow,
} from '../lib/planForm';
import type {
  InvestmentPlan,
  InvestmentPlanGoalPurpose,
  InvestmentPlanResponse,
} from '../types';

const INPUT = 'w-full border p-1 text-sm';
const SMALL_BUTTON = 'rounded bg-gray-200 px-2 py-1 text-sm text-slate-900';
const pct = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 2 });

const today = () => localDateISO();

const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);

type Patch<T> = (patch: Partial<T>) => void;

function TextInput({
  label,
  value,
  onChange,
  type = 'text',
  className = INPUT,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: 'text' | 'date' | 'number';
  className?: string;
}) {
  return (
    <input
      type={type}
      step={type === 'number' ? 'any' : undefined}
      className={className}
      value={value}
      placeholder={type === 'text' ? label.replace(/ \d+$/, '') : undefined}
      onChange={(e) => onChange(e.target.value)}
      aria-label={label}
    />
  );
}

function ClassSelect({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <select
      className={INPUT}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-label={label}
    >
      {/* Keep a class the list doesn't know (e.g. from pasted JSON) rather than show it as the first option. */}
      {[...(isPlanClass(value) ? [] : [value]), ...PLAN_CLASSES].map((key) => (
        <option key={key} value={key}>
          {classLabel(key)}
        </option>
      ))}
    </select>
  );
}

/** A titled list of editable rows with add and remove buttons. */
function RowList<T extends object>({
  title,
  itemName,
  hint,
  rows,
  onChange,
  blank,
  renderRow,
  footer,
}: {
  title: string;
  /** Lower-case singular name used in the add button. */
  itemName: string;
  hint?: string;
  rows: T[];
  onChange: (rows: T[]) => void;
  blank: () => T;
  renderRow: (row: T, patch: Patch<T>, n: number) => ReactNode;
  footer?: ReactNode;
}) {
  const { t } = useTranslation();
  const patchAt = (i: number) => (patch: Partial<T>) =>
    onChange(rows.map((row, j) => (j === i ? { ...row, ...patch } : row)));
  return (
    <fieldset className="mb-4">
      <legend className="font-medium">{title}</legend>
      {hint && (
        <p className="mb-1 text-xs text-slate-500 dark:text-slate-400">
          {hint}
        </p>
      )}
      {rows.map((row, i) => (
        <div key={i} className="mb-1 flex items-start gap-2">
          <div className="grid flex-1 gap-1 sm:grid-flow-col sm:auto-cols-fr">
            {renderRow(row, patchAt(i), i + 1)}
          </div>
          <button
            type="button"
            className={SMALL_BUTTON}
            onClick={() => onChange(rows.filter((_, j) => j !== i))}
            aria-label={t('planEditor.remove', {
              item: title.toLowerCase(),
              n: i + 1,
            })}
          >
            ✕
          </button>
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className={SMALL_BUTTON}
          onClick={() => onChange([...rows, blank()])}
        >
          {t('planEditor.add', { item: itemName })}
        </button>
        {footer}
      </div>
    </fieldset>
  );
}

function HeaderFields({ form, set }: { form: PlanForm; set: Patch<PlanForm> }) {
  const { t } = useTranslation();
  return (
    <div className="mb-4 grid gap-2 sm:grid-cols-3">
      <label className="text-sm">
        {t('planEditor.status')}
        <select
          className={INPUT}
          value={form.status}
          onChange={(e) =>
            set({ status: e.target.value as InvestmentPlan['status'] })
          }
        >
          {PLAN_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>
      <label className="text-sm">
        {t('planEditor.version')}
        <TextInput
          label={t('planEditor.version')}
          type="number"
          value={form.version}
          onChange={(version) => set({ version })}
        />
      </label>
      <label className="text-sm">
        {t('planEditor.nextReview')}
        <TextInput
          label={t('planEditor.nextReview')}
          type="date"
          value={form.next_review}
          onChange={(next_review) => set({ next_review })}
        />
      </label>
      <label className="text-sm sm:col-span-3">
        {t('planEditor.summary')}
        <textarea
          className={INPUT}
          rows={2}
          value={form.summary}
          onChange={(e) => set({ summary: e.target.value })}
        />
      </label>
    </div>
  );
}

function TargetSection({
  rows,
  onChange,
}: {
  rows: TargetRow[];
  onChange: (rows: TargetRow[]) => void;
}) {
  const { t } = useTranslation();
  const total = targetTotal(rows);
  const ok = Math.abs(total - 100) <= 0.01;
  const unused = PLAN_CLASSES.find((c) => !rows.some((r) => r.class === c));
  return (
    <RowList
      title={t('planEditor.targetTitle')}
      itemName={t('planEditor.targetItem')}
      rows={rows}
      onChange={onChange}
      blank={() => ({ class: unused ?? 'equity', weight: '' })}
      renderRow={(row, patch, n) => (
        <>
          <ClassSelect
            label={t('planEditor.targetClass', { n })}
            value={row.class}
            onChange={(cls) => patch({ class: cls })}
          />
          <TextInput
            label={t('planEditor.targetWeight', { n })}
            type="number"
            value={row.weight}
            onChange={(weight) => patch({ weight })}
          />
        </>
      )}
      footer={
        <span
          className={`text-sm ${ok ? '' : 'text-amber-700 dark:text-amber-300'}`}
          role="status"
        >
          {t('planEditor.total', { total: pct.format(total) })}{' '}
          {ok ? '' : t('planEditor.mustEqual100')}
        </span>
      }
    />
  );
}

function VehicleSection({
  rows,
  onChange,
  defaultClass,
}: {
  rows: VehicleRow[];
  onChange: (rows: VehicleRow[]) => void;
  defaultClass: string;
}) {
  const { t } = useTranslation();
  return (
    <RowList
      title={t('planEditor.vehiclesTitle')}
      itemName={t('planEditor.vehicleItem')}
      hint={t('planEditor.vehiclesHint')}
      rows={rows}
      onChange={onChange}
      blank={() => ({ class: defaultClass, ticker: '', note: '' })}
      renderRow={(row, patch, n) => (
        <>
          <ClassSelect
            label={t('planEditor.vehicleClass', { n })}
            value={row.class}
            onChange={(cls) => patch({ class: cls })}
          />
          <TextInput
            label={t('planEditor.ticker', { n })}
            value={row.ticker}
            onChange={(ticker) => patch({ ticker })}
          />
          <TextInput
            label={t('planEditor.note', { n })}
            value={row.note}
            onChange={(note) => patch({ note })}
          />
        </>
      )}
    />
  );
}

function AssumptionSection({
  rows,
  onChange,
}: {
  rows: AssumptionRow[];
  onChange: (rows: AssumptionRow[]) => void;
}) {
  const { t } = useTranslation();
  return (
    <RowList
      title={t('planEditor.assumptionsTitle')}
      itemName={t('planEditor.assumptionItem')}
      hint={t('planEditor.assumptionsHint')}
      rows={rows}
      onChange={onChange}
      blank={() => ({ key: '', value: '', note: '' })}
      renderRow={(row, patch, n) => (
        <>
          <TextInput
            label={t('planEditor.assumption', { n })}
            value={row.key}
            onChange={(key) => patch({ key })}
          />
          <TextInput
            label={t('planEditor.value', { n })}
            value={row.value}
            onChange={(value) => patch({ value })}
          />
          <TextInput
            label={t('planEditor.assumptionNote', { n })}
            value={row.note}
            onChange={(note) => patch({ note })}
          />
        </>
      )}
    />
  );
}

function DecisionSection({
  rows,
  onChange,
}: {
  rows: DecisionRow[];
  onChange: (rows: DecisionRow[]) => void;
}) {
  const { t } = useTranslation();
  return (
    <RowList
      title={t('planEditor.decisionsTitle')}
      itemName={t('planEditor.decisionItem')}
      rows={rows}
      onChange={onChange}
      blank={() => ({
        id: '',
        date: today(),
        decision: '',
        reason: '',
        alternatives: '',
      })}
      renderRow={(row, patch, n) => (
        <>
          <TextInput
            label={t('planEditor.decisionDate', { n })}
            type="date"
            value={row.date}
            onChange={(date) => patch({ date })}
          />
          <TextInput
            label={t('planEditor.decision', { n })}
            value={row.decision}
            onChange={(decision) => patch({ decision })}
          />
          <TextInput
            label={t('planEditor.reason', { n })}
            value={row.reason}
            onChange={(reason) => patch({ reason })}
          />
          <textarea
            className={INPUT}
            rows={1}
            placeholder={t('planEditor.alternativesPlaceholder')}
            aria-label={t('planEditor.alternatives', { n })}
            value={row.alternatives}
            onChange={(e) => patch({ alternatives: e.target.value })}
          />
        </>
      )}
    />
  );
}

function EvidenceSection({
  rows,
  onChange,
}: {
  rows: EvidenceRow[];
  onChange: (rows: EvidenceRow[]) => void;
}) {
  const { t } = useTranslation();
  const fields = ['metric', 'value', 'basis', 'source'] as const;
  return (
    <RowList
      title={t('planEditor.evidenceTitle')}
      itemName={t('planEditor.evidenceItem')}
      rows={rows}
      onChange={onChange}
      blank={() => ({
        as_of: today(),
        metric: '',
        value: '',
        basis: '',
        source: '',
      })}
      renderRow={(row, patch, n) => (
        <>
          <TextInput
            label={t('planEditor.evidenceAsOf', { n })}
            type="date"
            value={row.as_of}
            onChange={(as_of) => patch({ as_of })}
          />
          {fields.map((field) => (
            <TextInput
              key={field}
              label={t(`planEditor.evidence_${field}`, { n })}
              value={row[field]}
              onChange={(value) => patch({ [field]: value })}
            />
          ))}
        </>
      )}
    />
  );
}

function TextListSection({
  title,
  itemName,
  rows,
  onChange,
}: {
  title: string;
  itemName: string;
  rows: TextRow[];
  onChange: (rows: TextRow[]) => void;
}) {
  const { t } = useTranslation();
  return (
    <RowList
      title={title}
      itemName={itemName}
      rows={rows}
      onChange={onChange}
      blank={() => ({ text: '' })}
      renderRow={(row, patch, n) => (
        <TextInput
          label={t('planEditor.numbered', { label: title, n })}
          value={row.text}
          onChange={(text) => patch({ text })}
        />
      )}
    />
  );
}

function RatingInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: RatingFields;
  onChange: (value: RatingFields) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="text-sm">
      {label}
      <div className="grid gap-1 sm:grid-cols-[8rem_1fr]">
        <select
          className={INPUT}
          value={value.level}
          onChange={(e) =>
            onChange({
              ...value,
              level: e.target.value as RatingFields['level'],
            })
          }
          aria-label={t('planEditor.ratingLevel', { label })}
        >
          <option value="">{t('planEditor.notRecorded')}</option>
          {PROFILE_LEVELS.map((level) => (
            <option key={level} value={level}>
              {t(`planEditor.level_${level}`)}
            </option>
          ))}
        </select>
        <TextInput
          label={t('planEditor.ratingNote', { label })}
          value={value.note}
          onChange={(note) => onChange({ ...value, note })}
        />
      </div>
    </div>
  );
}

function GoalSection({
  rows,
  onChange,
}: {
  rows: GoalRow[];
  onChange: (rows: GoalRow[]) => void;
}) {
  const { t } = useTranslation();
  return (
    <RowList
      title={t('planEditor.goalsTitle')}
      itemName={t('planEditor.goalItem')}
      hint={t('planEditor.goalsHint')}
      rows={rows}
      onChange={onChange}
      blank={(): GoalRow => ({
        name: '',
        purpose: 'other',
        target_date: '',
        amount: '',
        priority: '',
        note: '',
      })}
      renderRow={(row, patch, n) => (
        <>
          <TextInput
            label={t('planEditor.goal', { n })}
            value={row.name}
            onChange={(name) => patch({ name })}
          />
          <select
            className={INPUT}
            value={row.purpose}
            onChange={(e) =>
              patch({ purpose: e.target.value as InvestmentPlanGoalPurpose })
            }
            aria-label={t('planEditor.goalPurpose', { n })}
          >
            {GOAL_PURPOSES.map((key) => (
              <option key={key} value={key}>
                {t(`planEditor.purpose_${key}`)}
              </option>
            ))}
          </select>
          <TextInput
            label={t('planEditor.goalTargetDate', { n })}
            type="date"
            value={row.target_date}
            onChange={(target_date) => patch({ target_date })}
          />
          <TextInput
            label={t('planEditor.goalAmount', { n })}
            type="number"
            value={row.amount}
            onChange={(amount) => patch({ amount })}
          />
          <TextInput
            label={t('planEditor.goalPriority', { n })}
            type="number"
            value={row.priority}
            onChange={(priority) => patch({ priority })}
          />
          <TextInput
            label={t('planEditor.goalNote', { n })}
            value={row.note}
            onChange={(note) => patch({ note })}
          />
        </>
      )}
    />
  );
}

/** Owner-stated profile (#9760): recorded as given, not assessed. */
function ProfileSection({
  form,
  set,
}: {
  form: PlanForm;
  set: Patch<PlanForm>;
}) {
  const { t } = useTranslation();
  return (
    <fieldset className="mb-4">
      <legend className="font-medium">{t('planEditor.profileTitle')}</legend>
      <p className="mb-1 text-xs text-slate-500 dark:text-slate-400">
        {t('planEditor.profileHint')}
      </p>
      <div className="mb-2 grid gap-2 sm:grid-cols-2">
        <RatingInput
          label={t('planEditor.riskTolerance')}
          value={form.risk_tolerance}
          onChange={(risk_tolerance) => set({ risk_tolerance })}
        />
        <RatingInput
          label={t('planEditor.capacityForLoss')}
          value={form.capacity_for_loss}
          onChange={(capacity_for_loss) => set({ capacity_for_loss })}
        />
      </div>
      <GoalSection rows={form.goals} onChange={(goals) => set({ goals })} />
    </fieldset>
  );
}

function PlanFormFields({
  form,
  set,
}: {
  form: PlanForm;
  set: Patch<PlanForm>;
}) {
  const { t } = useTranslation();
  return (
    <>
      <HeaderFields form={form} set={set} />
      <ProfileSection form={form} set={set} />
      <TargetSection
        rows={form.target}
        onChange={(target) => set({ target })}
      />
      <VehicleSection
        rows={form.vehicles}
        onChange={(vehicles) => set({ vehicles })}
        defaultClass={form.target[0]?.class ?? 'equity'}
      />
      <AssumptionSection
        rows={form.assumptions}
        onChange={(assumptions) => set({ assumptions })}
      />
      <DecisionSection
        rows={form.decisions}
        onChange={(decisions) => set({ decisions })}
      />
      <EvidenceSection
        rows={form.evidence}
        onChange={(evidence) => set({ evidence })}
      />
      <TextListSection
        title={t('planEditor.openQuestionsTitle')}
        itemName={t('planEditor.openQuestionItem')}
        rows={form.open_questions}
        onChange={(open_questions) => set({ open_questions })}
      />
      <TextListSection
        title={t('planEditor.triggersTitle')}
        itemName={t('planEditor.triggerItem')}
        rows={form.triggers}
        onChange={(triggers) => set({ triggers })}
      />
    </>
  );
}

/** Form state, its raw-JSON view, and the switch between them. */
function usePlanDraft(owner: string, initial: Partial<InvestmentPlan>) {
  const { t } = useTranslation();
  const [form, setForm] = useState(() => fromPlan(initial));
  const [json, setJson] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const set: Patch<PlanForm> = (patch) => setForm((f) => ({ ...f, ...patch }));

  /** Plan from the current mode, or null after reporting why it can't be built. */
  function currentPlan(): Partial<InvestmentPlan> | null {
    if (json === null) {
      const problems = formErrors(form);
      if (problems.length) {
        setError(problems.join(' '));
        return null;
      }
      return toPlan(form, owner, today());
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(json);
    } catch (err) {
      setError(t('planEditor.invalidJson', { message: errorText(err) }));
      return null;
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      setError(t('planEditor.invalidJsonObject'));
      return null;
    }
    return parsed as Partial<InvestmentPlan>;
  }

  function toggle() {
    setError(null);
    if (json === null) {
      setJson(JSON.stringify(toPlan(form, owner, today()), null, 2));
      return;
    }
    const plan = currentPlan();
    if (!plan) return;
    setForm(fromPlan(plan));
    setJson(null);
  }

  return { form, set, json, setJson, error, setError, currentPlan, toggle };
}

/**
 * Structured editor for the investment plan (#9655), with a raw JSON view for
 * pasting a whole plan. The backend validates the result either way.
 */
export default function PlanEditor({
  owner,
  initial,
  onSaved,
  onCancel,
}: {
  owner: string;
  initial: Partial<InvestmentPlan>;
  onSaved: (data: InvestmentPlanResponse) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const draft = usePlanDraft(owner, initial);
  const [saving, setSaving] = useState(false);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    draft.setError(null);
    const plan = draft.currentPlan();
    if (!plan) return;
    setSaving(true);
    try {
      onSaved(await saveInvestmentPlan(owner, plan));
    } catch (err) {
      draft.setError(errorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSave} aria-label={t('planEditor.formLabel')}>
      <div className="mb-3 flex justify-end">
        <button type="button" className={SMALL_BUTTON} onClick={draft.toggle}>
          {draft.json === null
            ? t('planEditor.editAsJson')
            : t('planEditor.backToForm')}
        </button>
      </div>
      {draft.json === null ? (
        <PlanFormFields form={draft.form} set={draft.set} />
      ) : (
        <textarea
          className="h-80 w-full border p-2 font-mono text-xs"
          value={draft.json}
          onChange={(e) => draft.setJson(e.target.value)}
          aria-label={t('planEditor.planJson')}
        />
      )}
      {draft.error && (
        <p className="mt-1 break-words text-sm text-red-600">{draft.error}</p>
      )}
      <div className="mt-2 flex gap-2">
        <button
          type="submit"
          disabled={saving}
          className="rounded bg-blue-500 px-4 py-1 text-white disabled:opacity-50"
        >
          {saving ? t('planEditor.saving') : t('planEditor.save')}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded bg-gray-200 px-3 py-1 text-slate-900"
        >
          {t('planEditor.cancel')}
        </button>
      </div>
    </form>
  );
}
