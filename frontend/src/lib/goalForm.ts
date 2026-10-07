export type Goal = {
  name: string;
  target_amount: number;
  target_date: string;
};

// Inputs hold raw strings so an empty amount stays empty instead of becoming
// NaN or a misleading default 0 (#7813).
export type GoalForm = { name: string; target_amount: string; target_date: string };

export const EMPTY_GOAL_FORM: GoalForm = { name: "", target_amount: "", target_date: "" };

/**
 * Format an ISO ``YYYY-MM-DD`` date in the active locale. The parts are built
 * into a local Date so the day never shifts across a UTC offset; anything
 * unparseable is shown as-is rather than dropped.
 */
export function formatGoalDate(iso: string, locale: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return iso;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(date);
}

/** Parse the form into a Goal, or null when a required field is missing/invalid. */
export function parseGoalForm(form: GoalForm): Goal | null {
  const name = form.name.trim();
  const amount = Number(form.target_amount);
  if (!name || !form.target_date || form.target_amount.trim() === "") return null;
  if (!Number.isFinite(amount) || amount <= 0) return null;
  return { name, target_amount: amount, target_date: form.target_date };
}
