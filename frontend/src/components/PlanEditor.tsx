import { useState, type ReactNode } from 'react';
import { saveInvestmentPlan } from '../api';
import {
  PLAN_CLASSES,
  PLAN_STATUSES,
  classLabel,
  formErrors,
  fromPlan,
  targetTotal,
  toPlan,
  type AssumptionRow,
  type DecisionRow,
  type EvidenceRow,
  type PlanForm,
  type TargetRow,
  type TextRow,
  type VehicleRow,
} from '../lib/planForm';
import type { InvestmentPlan, InvestmentPlanResponse } from '../types';

const INPUT = 'w-full border p-1 text-sm';
const SMALL_BUTTON = 'rounded bg-gray-200 px-2 py-1 text-sm text-slate-900';
const pct = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 2 });

const today = () => new Date().toISOString().slice(0, 10);

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
      {PLAN_CLASSES.map((key) => (
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
  hint,
  rows,
  onChange,
  blank,
  renderRow,
  footer,
}: {
  title: string;
  hint?: string;
  rows: T[];
  onChange: (rows: T[]) => void;
  blank: () => T;
  renderRow: (row: T, patch: Patch<T>, n: number) => ReactNode;
  footer?: ReactNode;
}) {
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
            aria-label={`Remove ${title.toLowerCase()} ${i + 1}`}
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
          Add {title.toLowerCase().replace(/s$/, '')}
        </button>
        {footer}
      </div>
    </fieldset>
  );
}

function HeaderFields({ form, set }: { form: PlanForm; set: Patch<PlanForm> }) {
  return (
    <div className="mb-4 grid gap-2 sm:grid-cols-3">
      <label className="text-sm">
        Status
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
        Version
        <TextInput
          label="Version"
          type="number"
          value={form.version}
          onChange={(version) => set({ version })}
        />
      </label>
      <label className="text-sm">
        Next review
        <TextInput
          label="Next review"
          type="date"
          value={form.next_review}
          onChange={(next_review) => set({ next_review })}
        />
      </label>
      <label className="text-sm sm:col-span-3">
        Summary
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
  const total = targetTotal(rows);
  const ok = Math.abs(total - 100) <= 0.01;
  const unused = PLAN_CLASSES.find((c) => !rows.some((r) => r.class === c));
  return (
    <RowList
      title="Target"
      rows={rows}
      onChange={onChange}
      blank={() => ({ class: unused ?? 'equity', weight: '' })}
      renderRow={(row, patch, n) => (
        <>
          <ClassSelect
            label={`Target class ${n}`}
            value={row.class}
            onChange={(cls) => patch({ class: cls })}
          />
          <TextInput
            label={`Target weight % ${n}`}
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
          Total: {pct.format(total)}% {ok ? '' : '(must equal 100%)'}
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
  return (
    <RowList
      title="Vehicles"
      hint="The instrument (ticker) or a placeholder note for each class."
      rows={rows}
      onChange={onChange}
      blank={() => ({ class: defaultClass, ticker: '', note: '' })}
      renderRow={(row, patch, n) => (
        <>
          <ClassSelect
            label={`Vehicle class ${n}`}
            value={row.class}
            onChange={(cls) => patch({ class: cls })}
          />
          <TextInput
            label={`Ticker ${n}`}
            value={row.ticker}
            onChange={(ticker) => patch({ ticker })}
          />
          <TextInput
            label={`Note ${n}`}
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
  return (
    <RowList
      title="Assumptions"
      hint="Numbers and true/false are saved as such; anything else as text."
      rows={rows}
      onChange={onChange}
      blank={() => ({ key: '', value: '', note: '' })}
      renderRow={(row, patch, n) => (
        <>
          <TextInput
            label={`Assumption ${n}`}
            value={row.key}
            onChange={(key) => patch({ key })}
          />
          <TextInput
            label={`Value ${n}`}
            value={row.value}
            onChange={(value) => patch({ value })}
          />
          <TextInput
            label={`Assumption note ${n}`}
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
  return (
    <RowList
      title="Decisions"
      rows={rows}
      onChange={onChange}
      blank={() => ({
        date: today(),
        decision: '',
        reason: '',
        alternatives: '',
      })}
      renderRow={(row, patch, n) => (
        <>
          <TextInput
            label={`Decision date ${n}`}
            type="date"
            value={row.date}
            onChange={(date) => patch({ date })}
          />
          <TextInput
            label={`Decision ${n}`}
            value={row.decision}
            onChange={(decision) => patch({ decision })}
          />
          <TextInput
            label={`Reason ${n}`}
            value={row.reason}
            onChange={(reason) => patch({ reason })}
          />
          <textarea
            className={INPUT}
            rows={1}
            placeholder="Alternatives rejected (one per line)"
            aria-label={`Alternatives ${n}`}
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
  const fields = ['metric', 'value', 'basis', 'source'] as const;
  return (
    <RowList
      title="Evidence"
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
            label={`Evidence as of ${n}`}
            type="date"
            value={row.as_of}
            onChange={(as_of) => patch({ as_of })}
          />
          {fields.map((field) => (
            <TextInput
              key={field}
              label={`Evidence ${field} ${n}`}
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
  rows,
  onChange,
}: {
  title: string;
  rows: TextRow[];
  onChange: (rows: TextRow[]) => void;
}) {
  return (
    <RowList
      title={title}
      rows={rows}
      onChange={onChange}
      blank={() => ({ text: '' })}
      renderRow={(row, patch, n) => (
        <TextInput
          label={`${title} ${n}`}
          value={row.text}
          onChange={(text) => patch({ text })}
        />
      )}
    />
  );
}

function PlanFormFields({
  form,
  set,
}: {
  form: PlanForm;
  set: Patch<PlanForm>;
}) {
  return (
    <>
      <HeaderFields form={form} set={set} />
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
        title="Open questions"
        rows={form.open_questions}
        onChange={(open_questions) => set({ open_questions })}
      />
      <TextListSection
        title="Review triggers"
        rows={form.triggers}
        onChange={(triggers) => set({ triggers })}
      />
    </>
  );
}

/** Form state, its raw-JSON view, and the switch between them. */
function usePlanDraft(owner: string, initial: Partial<InvestmentPlan>) {
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
      setError(`Invalid JSON: ${errorText(err)}`);
      return null;
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      setError('Invalid JSON: the plan must be a JSON object.');
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
    <form onSubmit={handleSave} aria-label="Edit investment plan">
      <div className="mb-3 flex justify-end">
        <button type="button" className={SMALL_BUTTON} onClick={draft.toggle}>
          {draft.json === null ? 'Edit as JSON' : 'Back to form'}
        </button>
      </div>
      {draft.json === null ? (
        <PlanFormFields form={draft.form} set={draft.set} />
      ) : (
        <textarea
          className="h-80 w-full border p-2 font-mono text-xs"
          value={draft.json}
          onChange={(e) => draft.setJson(e.target.value)}
          aria-label="Plan JSON"
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
          {saving ? 'Saving…' : 'Save plan'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded bg-gray-200 px-3 py-1 text-slate-900"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
