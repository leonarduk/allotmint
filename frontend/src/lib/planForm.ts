// Form state for the structured investment plan editor (#9655). Every input
// is held as text so a half-typed number survives re-renders; toPlan converts
// back to the backend's InvestmentPlan shape (backend/common/investment_plan.py).
import i18n from '../i18n';
import { classKeyLabel } from './assetClass';
import type {
  InvestmentPlan,
  InvestmentPlanGoalPurpose,
  InvestmentPlanProfile,
  InvestmentPlanProfileLevel,
  InvestmentPlanProfileRating,
  InvestmentPlanVehicle,
} from '../types';

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

export const isPlanClass = (key: string) =>
  (PLAN_CLASSES as readonly string[]).includes(key);

export const PLAN_STATUSES: InvestmentPlan['status'][] = [
  'draft',
  'active',
  'superseded',
];

/** Owner-stated levels for risk tolerance and capacity for loss (#9760). */
export const PROFILE_LEVELS: InvestmentPlanProfileLevel[] = [
  'low',
  'medium',
  'high',
];

/** Display labels for goal purposes (the editor translates them via planEditor.purpose_*). */
const GOAL_PURPOSE_LABELS: Record<InvestmentPlanGoalPurpose, string> = {
  retirement: 'Retirement',
  education: 'Education',
  house_deposit: 'House deposit',
  income: 'Income',
  general_wealth: 'General wealth',
  other: 'Other',
};

/** Goal purposes, in backend GoalPurpose order. */
export const GOAL_PURPOSES = Object.keys(
  GOAL_PURPOSE_LABELS
) as InvestmentPlanGoalPurpose[];

export const goalPurposeLabel = (key: string) =>
  key in GOAL_PURPOSE_LABELS ? i18n.t(`planEditor.purpose_${key}`) : key;

/** Plan class keys and the parent asset classes they roll up to. */
const CLASS_KEYS = new Set([
  'equity',
  // Policy key the plan's equity maps to beside small_cap_value (#9653).
  'broad_equity',
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
  'bond',
  'commodity',
  'property',
  'multi-asset',
]);

export const classLabel = (key: string) =>
  CLASS_KEYS.has(key) ? classKeyLabel(key) : key;

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
export interface GoalRow {
  name: string;
  purpose: InvestmentPlanGoalPurpose;
  target_date: string;
  amount: string;
  priority: string;
  note: string;
}
/** A profile rating as text; a blank level means "not recorded". */
export interface RatingFields {
  level: InvestmentPlanProfileLevel | '';
  note: string;
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
  risk_tolerance: RatingFields;
  capacity_for_loss: RatingFields;
  goals: GoalRow[];
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
    risk_tolerance: { level: '', note: '' },
    capacity_for_loss: { level: '', note: '' },
    goals: [],
  };
}

type VehicleInput = InvestmentPlanVehicle | string;

/** Flatten vehicles, accepting the backend's shorthand: a ticker string, alone or in a list. */
function vehicleRows(
  vehicles: Record<string, VehicleInput | VehicleInput[]> | undefined
): VehicleRow[] {
  return Object.entries(vehicles ?? {}).flatMap(([cls, items]) =>
    (Array.isArray(items) ? items : [items]).map((v) =>
      typeof v === 'string'
        ? { class: cls, ticker: v, note: '' }
        : { class: cls, ticker: v.ticker ?? '', note: v.note ?? '' }
    )
  );
}

const ratingFields = (
  rating: InvestmentPlanProfileRating | undefined
): RatingFields => ({ level: rating?.level ?? '', note: rating?.note ?? '' });

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
    vehicles: vehicleRows(plan.vehicles),
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
    risk_tolerance: ratingFields(plan.profile?.risk_tolerance),
    capacity_for_loss: ratingFields(plan.profile?.capacity_for_loss),
    goals: (plan.profile?.goals ?? []).map((g) => ({
      name: g.name,
      purpose: g.purpose,
      target_date: g.target_date ?? '',
      amount: scalarText(g.amount_gbp),
      priority: scalarText(g.priority),
      note: g.note ?? '',
    })),
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

/** A goal row with nothing typed in it (purpose always has a value, so it doesn't count). */
const isBlankGoal = ({ purpose: _purpose, ...rest }: GoalRow) => isBlank(rest);

/** Text -> number; blank is undefined (the form flags non-numbers before saving). */
const optionalNumber = (text: string) =>
  text.trim() ? Number(text.trim()) : undefined;

function ratingOf(
  fields: RatingFields
): InvestmentPlanProfileRating | undefined {
  if (!fields.level) return undefined;
  return { level: fields.level, note: optional(fields.note) };
}

/** The profile, or undefined when nothing is recorded so plans without one stay without one. */
function profileOf(form: PlanForm): InvestmentPlanProfile | undefined {
  const profile: InvestmentPlanProfile = {
    risk_tolerance: ratingOf(form.risk_tolerance),
    capacity_for_loss: ratingOf(form.capacity_for_loss),
    goals: form.goals
      .filter((g) => !isBlankGoal(g))
      .map((g) => ({
        name: g.name.trim(),
        purpose: g.purpose,
        target_date: optional(g.target_date),
        amount_gbp: optionalNumber(g.amount),
        priority: optionalNumber(g.priority),
        note: optional(g.note),
      })),
  };
  const empty =
    !profile.risk_tolerance &&
    !profile.capacity_for_loss &&
    !profile.goals.length;
  return empty ? undefined : profile;
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
        // A blank value is omitted from the JSON, so the backend reports it as missing.
        value: parseNumberOrText(e.value) as string | number,
        basis: optional(e.basis),
        source: optional(e.source),
      })),
    open_questions: texts(form.open_questions),
    review: {
      next_review: optional(form.next_review),
      triggers: texts(form.triggers),
    },
    profile: profileOf(form),
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
    errors.push(i18n.t('planForm.errors.version'));
  const bad = form.target.filter(
    (t) => t.weight.trim() && !NUMBER_RE.test(t.weight.trim())
  );
  if (bad.length)
    errors.push(
      i18n.t('planForm.errors.weightNotNumber', {
        cls: classLabel(bad[0].class),
      })
    );
  const classes = form.target.map((t) => t.class);
  const dupe = classes.find((c, i) => classes.indexOf(c) !== i);
  if (dupe)
    errors.push(
      i18n.t('planForm.errors.duplicateClass', { cls: classLabel(dupe) })
    );
  const total = targetTotal(form.target);
  if (!bad.length && Math.abs(total - 100) > TARGET_SUM_TOLERANCE_PCT)
    errors.push(
      i18n.t('planForm.errors.sum', {
        total: Math.round(total * 100) / 100,
      })
    );
  return [...errors, ...profileErrors(form)];
}

function ratingError(fields: RatingFields, message: string): string[] {
  return !fields.level && fields.note.trim() ? [message] : [];
}

function goalErrors(goal: GoalRow, n: number): string[] {
  const errors: string[] = [];
  const amount = goal.amount.trim();
  const priority = goal.priority.trim();
  if (!goal.name.trim()) errors.push(i18n.t('planForm.errors.goalName', { n }));
  if (amount && !(NUMBER_RE.test(amount) && Number(amount) >= 0))
    errors.push(i18n.t('planForm.errors.goalAmount', { n }));
  if (priority && !(/^\d+$/.test(priority) && Number(priority) >= 1))
    errors.push(i18n.t('planForm.errors.goalPriority', { n }));
  return errors;
}

function profileErrors(form: PlanForm): string[] {
  return [
    ...ratingError(
      form.risk_tolerance,
      i18n.t('planForm.errors.riskToleranceLevel')
    ),
    ...ratingError(
      form.capacity_for_loss,
      i18n.t('planForm.errors.capacityForLossLevel')
    ),
    ...form.goals.flatMap((g, i) =>
      isBlankGoal(g) ? [] : goalErrors(g, i + 1)
    ),
  ];
}
