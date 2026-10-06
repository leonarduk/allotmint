// Form state for the structured investment plan editor (#9655). Every input
// is held as text so a half-typed number survives re-renders; toPlan converts
// back to the backend's InvestmentPlan shape (backend/common/investment_plan.py).
import type { InvestmentPlan } from '../types';

/** Plan class keys, in backend PLAN_CLASS_PARENT order. */
export const PLAN_CLASSES = [
  'equity',
  'small_cap_value',
  'long_gilts',
  'intermediate_gilts',
  'short_gilts',
  'index_linked',
  'overseas_government',
  'corporate_bonds',
  'gold',
  'commodities',
  'cash',
] as const;

export const PLAN_STATUSES: InvestmentPlan['status'][] = [
  'draft',
  'active',
  'superseded',
];

/** Labels for plan class keys and the parent asset classes they roll up to. */
const CLASS_LABELS: Record<string, string> = {
  equity: 'Equity',
  small_cap_value: 'Small-cap value',
  long_gilts: 'Long gilts',
  intermediate_gilts: 'Intermediate gilts',
  short_gilts: 'Short gilts / ultrashort',
  index_linked: 'Index-linked',
  overseas_government: 'Overseas government',
  corporate_bonds: 'Corporate / credit',
  gold: 'Gold',
  commodities: 'Other commodities',
  cash: 'Cash',
  bond: 'Bond',
  commodity: 'Commodity',
  property: 'Property',
  'multi-asset': 'Multi-asset',
};

export const classLabel = (key: string) => CLASS_LABELS[key] ?? key;

export interface TargetRow {
  class: string;
  weight: string;
}
export interface VehicleRow {
  class: string;
  ticker: string;
  note: string;
}
export interface AssumptionRow {
  key: string;
  value: string;
  note: string;
}
export interface DecisionRow {
  date: string;
  decision: string;
  reason: string;
  /** One alternative per line. */
  alternatives: string;
}
export interface EvidenceRow {
  as_of: string;
  metric: string;
  value: string;
  basis: string;
  source: string;
}
export interface TextRow {
  text: string;
}

export interface PlanForm {
  version: string;
  status: InvestmentPlan['status'];
  summary: string;
  next_review: string;
  disclaimer?: string;
  target: TargetRow[];
  vehicles: VehicleRow[];
  assumptions: AssumptionRow[];
  decisions: DecisionRow[];
  evidence: EvidenceRow[];
  open_questions: TextRow[];
  triggers: TextRow[];
}

/** Same slack as backend TARGET_SUM_TOLERANCE_PCT. */
const TARGET_SUM_TOLERANCE_PCT = 0.01;

const NUMBER_RE = /^-?\d+(\.\d+)?$/;

/** Text -> scalar: numbers and true/false keep their JSON type; blank is undefined. */
/** Text -> number when it is one, else trimmed text; blank is undefined (evidence values take no booleans). */
export function parseNumberOrText(text: string): string | number | undefined {
  const trimmed = text.trim();
  if (!trimmed) return undefined;
  return NUMBER_RE.test(trimmed) ? Number(trimmed) : trimmed;
}

export function parseScalar(
  text: string
): string | number | boolean | undefined {
  const trimmed = text.trim();
  if (!trimmed) return undefined;
  if (trimmed === 'true') return true;
  if (trimmed === 'false') return false;
  return NUMBER_RE.test(trimmed) ? Number(trimmed) : trimmed;
}

const scalarText = (value: unknown) => (value == null ? '' : String(value));

/** Undefined for blank text, so optional fields are omitted rather than sent as "". */
const optional = (text: string) => text.trim() || undefined;

const isBlank = (row: object) =>
  Object.values(row).every((v) => typeof v !== 'string' || !v.trim());

const texts = (rows: TextRow[]) =>
  rows.map((r) => r.text.trim()).filter(Boolean);

export function emptyPlanForm(): PlanForm {
  return {
    version: '1',
    status: 'draft',
    summary: '',
    next_review: '',
    target: [{ class: 'equity', weight: '100' }],
    vehicles: [],
    assumptions: [],
    decisions: [],
    evidence: [],
    open_questions: [],
    triggers: [],
  };
}

export function fromPlan(plan: Partial<InvestmentPlan>): PlanForm {
  const base = emptyPlanForm();
  return {
    version: plan.version != null ? String(plan.version) : base.version,
    status: plan.status ?? base.status,
    summary: plan.summary ?? '',
    next_review: plan.review?.next_review ?? '',
    disclaimer: plan.disclaimer,
    target: plan.target
      ? plan.target.map((t) => ({
          class: t.class,
          weight: String(t.weight_pct),
        }))
      : base.target,
    vehicles: Object.entries(plan.vehicles ?? {}).flatMap(([cls, list]) =>
      list.map((v) => ({
        class: cls,
        ticker: v.ticker ?? '',
        note: v.note ?? '',
      }))
    ),
    assumptions: (plan.assumptions ?? []).map((a) => ({
      key: a.key,
      value: scalarText(a.value),
      note: a.note ?? '',
    })),
    decisions: (plan.decisions ?? []).map((d) => ({
      date: d.date,
      decision: d.decision,
      reason: d.reason ?? '',
      alternatives: (d.alternatives ?? []).join('\n'),
    })),
    evidence: (plan.evidence ?? []).map((e) => ({
      as_of: e.as_of,
      metric: e.metric,
      value: scalarText(e.value),
      basis: e.basis ?? '',
      source: e.source ?? '',
    })),
    open_questions: (plan.open_questions ?? []).map((text) => ({ text })),
    triggers: (plan.review?.triggers ?? []).map((text) => ({ text })),
  };
}

function vehiclesOf(rows: VehicleRow[]): InvestmentPlan['vehicles'] {
  const out: InvestmentPlan['vehicles'] = {};
  for (const row of rows.filter((r) => !isBlank({ t: r.ticker, n: r.note }))) {
    (out[row.class] ??= []).push({
      ticker: optional(row.ticker),
      note: optional(row.note),
    });
  }
  return out;
}

/** Plan payload; the backend fills in its default disclaimer when none is sent. */
export type PlanPayload = Omit<InvestmentPlan, 'disclaimer'> & {
  disclaimer?: string;
};

/** Form -> plan payload. Rows left entirely blank are dropped; `updated` is today. */
export function toPlan(
  form: PlanForm,
  owner: string,
  today: string
): PlanPayload {
  return {
    owner,
    version: Number(form.version),
    updated: today,
    status: form.status,
    summary: form.summary.trim(),
    target: form.target
      .filter((t) => t.weight.trim())
      .map((t) => ({ class: t.class, weight_pct: Number(t.weight) })),
    vehicles: vehiclesOf(form.vehicles),
    assumptions: form.assumptions
      .filter((a) => !isBlank(a))
      .map((a) => ({
        key: a.key.trim(),
        value: parseScalar(a.value),
        note: optional(a.note),
      })),
    decisions: form.decisions
      .filter((d) => !isBlank(d))
      .map((d) => ({
        date: d.date,
        decision: d.decision.trim(),
        reason: optional(d.reason),
        alternatives: d.alternatives
          .split('\n')
          .map((s) => s.trim())
          .filter(Boolean),
      })),
    evidence: form.evidence
      .filter((e) => !isBlank(e))
      .map((e) => ({
        as_of: e.as_of,
        metric: e.metric.trim(),
        // Blank is left for the backend to reject as a missing value.
        value: parseNumberOrText(e.value) as string | number,
        basis: optional(e.basis),
        source: optional(e.source),
      })),
    open_questions: texts(form.open_questions),
    review: {
      next_review: optional(form.next_review),
      triggers: texts(form.triggers),
    },
    ...(form.disclaimer ? { disclaimer: form.disclaimer } : {}),
  };
}

/** Sum of the target weights that parse as numbers. */
export function targetTotal(rows: TargetRow[]): number {
  return rows.reduce((sum, r) => {
    const weight = r.weight.trim();
    return NUMBER_RE.test(weight) ? sum + Number(weight) : sum;
  }, 0);
}

/** Problems the form can catch before the save round trip; the backend still validates everything. */
export function formErrors(form: PlanForm): string[] {
  const errors: string[] = [];
  if (!/^\d+$/.test(form.version.trim()) || Number(form.version) < 1)
    errors.push('Version must be a whole number of at least 1.');
  const bad = form.target.filter(
    (t) => t.weight.trim() && !NUMBER_RE.test(t.weight.trim())
  );
  if (bad.length)
    errors.push(
      `Target weight for ${classLabel(bad[0].class)} is not a number.`
    );
  const classes = form.target.map((t) => t.class);
  const dupe = classes.find((c, i) => classes.indexOf(c) !== i);
  if (dupe)
    errors.push(`${classLabel(dupe)} appears more than once in the target.`);
  const total = targetTotal(form.target);
  if (!bad.length && Math.abs(total - 100) > TARGET_SUM_TOLERANCE_PCT)
    errors.push(
      `Target weights must sum to 100%, got ${Math.round(total * 100) / 100}%.`
    );
  return errors;
}
