// Draft state for the rebalance target editor (#9543). A splittable class
// (Bond, Commodity) is targeted either as a whole or by its sub-classes; the
// backend rejects a policy that does both, so only the active level is saved.
import { SUB_ASSET_CLASSES } from './assetClass';
import type { RebalancePlan } from '../types';

/** Canonical asset classes, matching backend ASSET_CLASSES / ASSET_CLASS_LABELS. */
export const ASSET_CLASSES: Array<{ key: string; label: string }> = [
  { key: 'equity', label: 'Equity' },
  { key: 'bond', label: 'Bond' },
  { key: 'cash', label: 'Cash' },
  { key: 'commodity', label: 'Commodity' },
  { key: 'property', label: 'Property' },
  { key: 'multi-asset', label: 'Multi-asset' },
];

const ALL_KEYS = ASSET_CLASSES.flatMap(({ key }) => [
  key,
  ...(SUB_ASSET_CLASSES[key] ?? []).map((sub) => sub.key),
]);

export interface TargetDraft {
  /** Raw input text for every class and sub-class key. */
  values: Record<string, string>;
  /** Classes currently targeted by sub-class. */
  split: string[];
}

const parsePct = (value: string | undefined): number => {
  const parsed = parseFloat(value ?? '');
  return Number.isFinite(parsed) ? parsed : 0;
};

const round2 = (value: number): number => Math.round(value * 100) / 100;

function draftValues(weights: Record<string, number>): Record<string, string> {
  return Object.fromEntries(
    ALL_KEYS.map((key) => [
      key,
      weights[key] != null ? String(weights[key]) : '',
    ])
  );
}

/** Draft for a saved policy: a class is split when any sub-class has a target. */
export function draftFromTargets(targets: Record<string, number>): TargetDraft {
  const split = Object.keys(SUB_ASSET_CLASSES).filter((parent) =>
    SUB_ASSET_CLASSES[parent].some((sub) => targets[sub.key] != null)
  );
  return { values: draftValues(targets), split };
}

/** Keys whose inputs count towards the total, in display order. */
export function activeKeys(split: string[]): string[] {
  return ASSET_CLASSES.flatMap(({ key }) =>
    split.includes(key) ? SUB_ASSET_CLASSES[key].map((sub) => sub.key) : [key]
  );
}

/** Sum of a split class's sub-class inputs. */
export function splitTotal(draft: TargetDraft, parent: string): number {
  return (SUB_ASSET_CLASSES[parent] ?? []).reduce(
    (sum, sub) => sum + parsePct(draft.values[sub.key]),
    0
  );
}

export function draftTotal(draft: TargetDraft): number {
  return activeKeys(draft.split).reduce(
    (sum, key) => sum + parsePct(draft.values[key]),
    0
  );
}

/** Positive targets at the active level, as sent to the backend. */
export function targetsFromDraft(draft: TargetDraft): Record<string, number> {
  const targets: Record<string, number> = {};
  for (const key of activeKeys(draft.split)) {
    const value = parsePct(draft.values[key]);
    if (value > 0) targets[key] = value;
  }
  return targets;
}

/**
 * Split ``parent`` into sub-classes, or combine it back. Combining carries
 * the sub-class total into the class input so the overall total is kept.
 */
export function toggleSplit(draft: TargetDraft, parent: string): TargetDraft {
  if (!draft.split.includes(parent)) {
    return { ...draft, split: [...draft.split, parent] };
  }
  const anySubSet = SUB_ASSET_CLASSES[parent].some((sub) =>
    draft.values[sub.key]?.trim()
  );
  const values = anySubSet
    ? { ...draft.values, [parent]: String(round2(splitTotal(draft, parent))) }
    : draft.values;
  return { values, split: draft.split.filter((p) => p !== parent) };
}

/**
 * Current weight (percent) of every class and held sub-class. A split
 * class's weight is the sum of its sub-class rows, including holdings with
 * no known sub-class.
 */
export function currentWeights(plan: RebalancePlan): Record<string, number> {
  const weights: Record<string, number> = {};
  for (const row of plan.sub_classes ?? []) {
    weights[row.parent] = round2((weights[row.parent] ?? 0) + row.current_pct);
    if (row.asset_class !== row.parent)
      weights[row.asset_class] = row.current_pct;
  }
  for (const row of plan.classes) {
    if (row.parent == null) weights[row.asset_class] = row.current_pct;
  }
  return weights;
}

/** Fill every input from the current allocation, keeping the split choice. */
export function draftFromCurrent(
  plan: RebalancePlan,
  split: string[]
): TargetDraft {
  return { values: draftValues(currentWeights(plan)), split };
}
